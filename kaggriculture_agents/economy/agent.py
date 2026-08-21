"""
agent.py — EconomyAgent, point d'entrée public du module.

API publique :

    economy_agent = EconomyAgent()
    proposals = economy_agent.decide(
        state, crop_proposals, animal_proposals, market_proposals,
    )   # -> list[EconomyProposal]

EconomyAgent lit uniquement FarmState et les propositions déjà produites
par CropAgent / AnimalAgent / MarketAgent (jamais `obs` directement, jamais
d'appel direct à ces agents, spec section 30). Il ne modifie ni FarmState
ni les propositions reçues, et ne produit/n'exécute AUCUNE action
Kaggriculture : seulement des EconomyProposal, consommées plus tard par le
futur PlannerAgent.
"""

from dataclasses import replace
from typing import List, Sequence

from .analyzers import analyze_budget, analyze_resources, evaluate_animal_proposals, evaluate_crop_proposals, evaluate_market_proposals, evaluate_investment_proposals
from .constants import BUDGET_CONFLICT_PENALTY
from .models import EconomyProposal
from .calendar import TaskCalendar
from .temporal import EconomicSchedule
from .strategic import build_strategic_economy


class EconomyAgent:
    """Agent de synthèse : évalue économiquement les opportunités détectées par les agents spécialisés."""

    def decide(
        self,
        state,
        crop_proposals: Sequence = (),
        animal_proposals: Sequence = (),
        market_proposals: Sequence = (),
        investment_proposals: Sequence = (),
        calendar: TaskCalendar | None = None,
    ) -> List[EconomyProposal]:
        if calendar is not None:
            calendar.observe(state)
            calendar.forecast(state)
        budget = analyze_budget(state)
        resource_levels = analyze_resources(state)
        strategic = build_strategic_economy(state)

        proposals: List[EconomyProposal] = []
        proposals += evaluate_crop_proposals(state, crop_proposals, budget)
        proposals += evaluate_animal_proposals(state, animal_proposals, budget)
        proposals += evaluate_market_proposals(
            state, market_proposals, budget, resource_levels, crop_proposals, animal_proposals,
        )
        proposals += evaluate_investment_proposals(state, investment_proposals, budget)

        # PRODUCE est un signal économique générique. Lorsqu'un PLANT concret
        # du CropAgent existe pour le même produit, conserver les deux ne fait
        # qu'alimenter le Planner avec un doublon qui sera rejeté plus tard.
        planted_products = {
            p.product for p in crop_proposals
            if getattr(p, "action", None) == "PLANT" and getattr(p, "product", None)
        }
        if planted_products:
            proposals = [
                p for p in proposals
                if not (getattr(p, "action", None) == "PRODUCE" and getattr(p, "product", None) in planted_products)
            ]

        # Analyse de portefeuille : l'économie considère désormais les
        # chaînes de tâches ensemble, et pas seulement chaque action isolée.
        proposals = self._evaluate_task_portfolios(state, proposals)
        if calendar is not None:
            proposals = self._apply_calendar_memory(state, proposals, calendar)
            schedule = calendar.economic_schedule(state)
            proposals = self._apply_temporal_portfolio_value(state, proposals, schedule)
        proposals = self._apply_budget_conflicts(proposals, min(budget.safe_budget, max(0.0, strategic.terminal_wealth - strategic.reserved_cash)))
        proposals = self._apply_shadow_prices(proposals, strategic.shadow_prices)
        proposals = self._apply_marginal_labor(proposals, strategic.marginal_worker_values)
        return self._sort_proposals(proposals)

    @staticmethod
    def _apply_shadow_prices(proposals, shadow_prices):
        out = []
        for p in proposals:
            sp = float(shadow_prices.get(p.product, 0.0)) if p.product else 0.0
            if p.action == "SELL" and sp > 0 and p.cash_delta < sp * max(1.0, p.quantity) * 0.95:
                out.append(replace(p, economic_score=max(0.0, p.economic_score - 0.08),
                    risk=min(1.0, p.risk + 0.05), reason=p.reason + f" ; shadow-price={sp:.0f}$"))
            else: out.append(p)
        return out

    @staticmethod
    def _apply_marginal_labor(proposals, worker_values):
        # Expensive labor is discouraged when the proposal does not create enough
        # incremental value. Only market HIRE proposals are affected.
        out=[]; idx=0
        for p in proposals:
            if p.action == "HIRE":
                mv = worker_values[min(idx, len(worker_values)-1)] if worker_values else 0.0
                idx += 1
                if mv < p.cost:
                    out.append(replace(p, economic_score=max(0.0, p.economic_score-0.15),
                        risk=min(1.0,p.risk+0.08), reason=p.reason + f" ; marginal-worker={mv:.1f}$ < cost={p.cost:.1f}$"))
                else: out.append(p)
            else: out.append(p)
        return out

    @staticmethod
    def _evaluate_task_portfolios(state, proposals: List[EconomyProposal]) -> List[EconomyProposal]:
        """Valorise des chaînes d'actions rentables comme des portefeuilles.

        Exemple central : acheter un animal peut sembler coûteux seul, mais
        devient très rentable lorsqu'il permet BUY/PLACE -> FEED/CARE ->
        HARVEST -> SELL et, surtout, COLLECT_FERTILIZER -> FERTILIZE. La
        valeur de la synergie est répartie sur les membres existants du
        portefeuille ; aucun nouvel ordre artificiel n'est créé ici.
        """
        if not proposals:
            return proposals
        result = list(proposals)

        def by(action, product=None, source=None):
            return [p for p in result if p.action == action
                    and (product is None or p.product == product)
                    and (source is None or p.source_agent == source)]

        def apply_bundle(members, bundle_id, synergy, net_value):
            if not members or synergy <= 0:
                return
            ids = {id(p) for p in members}
            bonus = min(0.22, max(0.0, synergy) / 4000.0)
            for i, p in enumerate(result):
                if id(p) not in ids:
                    continue
                result[i] = replace(
                    p,
                    economic_score=min(1.0, p.economic_score + bonus),
                    synergy_bonus=p.synergy_bonus + bonus,
                    bundle_id=p.bundle_id or bundle_id,
                    bundle_role=p.bundle_role or p.action,
                    bundle_net_value=max(p.bundle_net_value, net_value),
                    reason=p.reason + f" ; portefeuille {bundle_id}: synergie +{synergy:.0f}$, valeur nette ~{net_value:.0f}$",
                )

        # Culture : achat de semences + plantation + récolte + vente.
        products = sorted({p.product for p in result if p.product})
        for product in products:
            seeds = by("BUY_SEED", product)
            plants = by("PLANT", product, "crop")
            harvests = by("HARVEST", product, "crop")
            sells = by("SELL", product)
            if not plants or not harvests or not sells:
                continue
            members = ([seeds[0]] if seeds else []) + [plants[0], harvests[0], sells[0]]
            gross = sum(float(p.expected_revenue) for p in members if p.action in {"HARVEST", "SELL"})
            costs = sum(float(p.cost) for p in members if p.action == "BUY_SEED")
            net = gross - costs
            intrinsic = sum(float(p.expected_profit) for p in members)
            synergy = max(0.0, net - intrinsic) + min(350.0, max(0.0, net) * 0.08)
            apply_bundle(members, f"CROP:{product}", synergy, net)

        # Elevage : achat -> installation/soins -> récolte -> vente.
        product_of = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
        for animal in sorted({p.product for p in result if p.action == "BUY_ANIMAL" and p.product}):
            buys = by("BUY_ANIMAL", animal)
            product = product_of.get(animal)
            if not buys or not product:
                continue
            members = [buys[0]]
            members += by("BUILD_COOP", animal)[:1] + by("BUILD_PASTURE", animal)[:1]
            members += by("PLACE", animal)[:1]
            members += by("FEED", animal, "animal")[:1]
            members += by("CARE", animal, "animal")[:1]
            animal_h = by("HARVEST", animal, "animal")[:1]
            members += animal_h
            members += by("SELL", product)[:1]
            if len(members) < 3:
                continue
            gross = sum(float(p.expected_revenue) for p in members if p.action == "SELL")
            gross += sum(float(p.expected_revenue) for p in animal_h)
            net = gross - float(buys[0].cost)
            synergy = min(500.0, max(0.0, net) * 0.10)
            apply_bundle(members, f"ANIMAL:{animal}", synergy, net)

            # Boucle circulaire : le fertilisant animal remplace l'achat marché
            # et permet de pousser le rendement des cultures.
            collects = by("COLLECT_FERTILIZER", animal, "animal")
            ferts = by("FERTILIZE", source="crop")
            if ferts:
                fert_price = float(state.market.prices.get("FERTILIZER", 100.0))
                if collects:
                    count = min(len(collects), len(ferts))
                    saving = count * fert_price
                    yield_value = sum(float(p.expected_revenue) for p in ferts[:count])
                    circular_members = [buys[0], collects[0], ferts[0]] + animal_h
                    circular_synergy = saving + min(600.0, max(0.0, yield_value) * 0.10)
                    apply_bundle(circular_members, f"CIRCULAR:FERTILIZER:{animal}", circular_synergy, net + circular_synergy)
                else:
                    # L'animal n'a pas encore de fertilisant disponible dans
                    # l'observation courante, mais l'achat peut créer la boucle
                    # à moyen terme. On ne valorise qu'une unité future si le
                    # temps restant permet d'atteindre le premier cycle animal.
                    first_yield = {"GOOSE": 4, "COW": 8, "SHEEP": 6}.get(animal, 999)
                    if state.time.remaining_days >= first_yield and ferts:
                        future_saving = fert_price
                        circular_members = [buys[0], ferts[0]]
                        circular_synergy = future_saving * 0.75
                        apply_bundle(circular_members, f"FUTURE:CIRCULAR:FERTILIZER:{animal}", circular_synergy, net + circular_synergy)

                # Si l'animal peut couvrir au moins une unité du besoin futur,
                # l'achat de fertilisant perd sa priorité économique.
                future_cover = fert_price if (collects or state.time.remaining_days >= {"GOOSE":4,"COW":8,"SHEEP":6}.get(animal,999)) else 0.0
                for p in by("BUY_PRODUCT", "FERTILIZER"):
                    if future_cover <= 0:
                        continue
                    idx = result.index(p)
                    result[idx] = replace(
                        p,
                        economic_score=max(0.0, p.economic_score - min(0.35, future_cover / 1000.0)),
                        reason=p.reason + f" ; économie circulaire anticipée : {animal} peut produire du fertilisant (~{future_cover:.0f}$ d'achat évitable)",
                    )

        # Boucle alimentaire : produire du blé puis nourrir l'élevage évite
        # d'acheter le même blé au marché.
        wheat_h = by("HARVEST", "WHEAT", "crop")
        feeds = by("FEED", source="animal")
        if wheat_h and feeds:
            count = min(len(wheat_h), len(feeds))
            wheat_price = float(state.market.prices.get("WHEAT", 25.0))
            saving = count * wheat_price
            members = wheat_h[:count] + feeds[:count] + by("PLANT", "WHEAT", "crop")[:1]
            net = saving + sum(float(p.expected_profit) for p in members)
            apply_bundle(members, "CIRCULAR:WHEAT", saving + min(250.0, max(0.0, net) * 0.05), net)
            for p in by("BUY_PRODUCT", "WHEAT"):
                idx = result.index(p)
                result[idx] = replace(
                    p,
                    economic_score=max(0.0, p.economic_score - min(0.30, saving / 500.0)),
                    reason=p.reason + f" ; substitution interne : blé produit à la ferme (~{saving:.0f}$ évitables)",
                )

        return result

    @staticmethod
    def _apply_budget_conflicts(proposals: List[EconomyProposal], safe_budget: float) -> List[EconomyProposal]:
        """
        Détection de conflit budgétaire (spec section 31-32) : les
        propositions engageant un coût réel sont examinées par ordre de
        score décroissant ; celles qui feraient dépasser le budget
        sécurisé une fois les meilleures déjà "réservées" sont marquées
        `budget_constrained=True` et pénalisées, SANS être retirées de la
        liste (le choix final de combinaison appartient au PlannerAgent).
        """
        ordered = sorted(proposals, key=lambda p: (-p.economic_score, p.action, str(p.target)))
        cumulative_cost = 0.0
        result: List[EconomyProposal] = []

        for p in ordered:
            if p.cost > 0:
                if cumulative_cost + p.cost > safe_budget:
                    p = replace(
                        p,
                        budget_constrained=True,
                        economic_score=p.economic_score * BUDGET_CONFLICT_PENALTY,
                        reason=p.reason + " ; contrainte budgétaire : dépasse le budget sécurisé restant",
                    )
                else:
                    cumulative_cost += p.cost
            result.append(p)
        return result

    @staticmethod
    def _apply_calendar_memory(state, proposals: List[EconomyProposal], calendar: TaskCalendar) -> List[EconomyProposal]:
        """Intègre la mémoire temporelle sans créer d'actions artificielles.

        Les achats redondants perdent du score ; les tâches dont le calendrier
        indique qu'elles sont dues maintenant gagnent du score. Cela permet au
        Planner de préférer COLLECT_FERTILIZER/HARVEST/FEED à un BUY_PRODUCT
        lorsque la ferme possède déjà la capacité de produire la ressource.
        """
        result = []
        for proposal in proposals:
            penalty, reason = calendar.purchase_penalty(
                state, proposal.action, proposal.product, getattr(proposal, "quantity", 1.0)
            )
            temporal = calendar.task_priority(state, proposal.action, proposal.product)
            score = float(proposal.economic_score)
            score = max(0.0, min(1.0, score * (1.0 - 0.75 * penalty) + 0.12 * temporal))
            if penalty > 0:
                reason_text = proposal.reason + " ; mémoire-calendrier : " + reason
            else:
                reason_text = proposal.reason
            if temporal >= 0.9:
                reason_text += f" ; tâche due maintenant (priorité temporelle {temporal:.2f})"
            result.append(replace(proposal, economic_score=score, reason=reason_text))
        return result

    @staticmethod
    def _apply_temporal_portfolio_value(state, proposals: List[EconomyProposal], schedule: EconomicSchedule) -> List[EconomyProposal]:
        """Valorise le portefeuille selon les besoins futurs et les synergies."""
        result: List[EconomyProposal] = []
        internal_value = {}
        for op in schedule.opportunities:
            internal_value[op.resource] = internal_value.get(op.resource, 0.0) + max(0.0, op.net_value)

        for p in proposals:
            score = float(p.economic_score)
            reason = p.reason
            if p.action in {"BUY_PRODUCT", "BUY_SEED"} and p.product:
                resource = p.product if p.action == "BUY_PRODUCT" else f"SEED_{p.product}"
                avoid = schedule.avoidable_purchase(resource)
                if avoid > 0:
                    penalty = min(0.38, 0.10 + avoid / max(10.0, float(p.quantity) * 10.0) * 0.08)
                    score *= (1.0 - penalty)
                    reason += f" ; calendrier futur : {avoid:.0f} unité(s) couvertes en interne, achat non prioritaire"

            produced = None
            if p.action == "COLLECT_FERTILIZER":
                produced = "FERTILIZER"
            elif p.action == "HARVEST":
                produced = p.product if p.source_agent == "crop" else {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}.get(p.product)
            if produced and produced in internal_value:
                bonus = min(0.20, internal_value[produced] / 3000.0)
                score = min(1.0, score + bonus)
                reason += f" ; valeur temporelle : {produced} répond à un besoin futur"

            # L'historique mesure aussi le coût déjà engagé : un second achat
            # du même intrant doit être justifié par un besoin supplémentaire,
            # pas seulement par son ROI instantané.
            if p.action in {"BUY_PRODUCT", "BUY_SEED", "BUY_ANIMAL"} and p.product:
                # schedule.projected_resources inclut le stock et les productions
                # futures ; une ressource déjà largement couverte ne mérite pas
                # une nouvelle dépense immédiate.
                projected = float(schedule.projected_resources.get(p.product, 0.0))
                if projected >= float(getattr(p, "quantity", 1.0)) and p.action == "BUY_PRODUCT":
                    score *= 0.82
                    reason += f" ; stock/projection temporelle {projected:.0f} {p.product} déjà disponible"

            if p.action == "BUY_ANIMAL" and internal_value.get("FERTILIZER", 0.0) > 0:
                fert = internal_value["FERTILIZER"]
                bonus = min(0.16, fert / 3500.0)
                score = min(1.0, score + bonus)
                reason += f" ; synergie future élevage→fertilisant : +{fert:.0f}$"

            result.append(replace(p, economic_score=max(0.0, min(1.0, score)), reason=reason))
        return result

    @staticmethod
    def _sort_proposals(proposals: List[EconomyProposal]) -> List[EconomyProposal]:
        """
        Tri déterministe (spec section 39) : economic_score DESC,
        expected_profit DESC, urgency DESC, risk ASC, puis action/target
        pour départager les égalités.
        """
        return sorted(
            proposals,
            key=lambda p: (-p.economic_score, -p.expected_profit, -p.urgency, p.risk, p.action, str(p.target)),
        )