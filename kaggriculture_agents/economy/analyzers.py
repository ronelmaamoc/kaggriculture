"""
analyzers.py — Analyse budgétaire/ressources et évaluation économique des
propositions issues de CropAgent / AnimalAgent / MarketAgent.

    analyze_budget(state)                       -> BudgetAnalysis
    analyze_resources(state)                    -> dict[str, "CRITICAL"|"LIMITED"|"ABUNDANT"]
    evaluate_crop_proposals(...)                 -> EconomyProposal[]
    evaluate_animal_proposals(...)                -> EconomyProposal[]
    evaluate_market_proposals(...)                -> EconomyProposal[]

Chaque evaluate_*_proposals() enveloppe une proposition source (jamais
modifiée) dans une évaluation économique indépendante. Aucune fonction ici
n'exécute d'action de jeu, ne modifie `state`, ni les propositions reçues
(spec sections 5 et 30 : lecture seule, aucun appel direct aux agents
spécialisés).
"""

from typing import Dict, List, Optional, Sequence

from . import scoring
from .constants import (
    ANIMAL_FIRST_YIELD_DAY,
    ANIMAL_PRODUCT,
    ANIMAL_PURCHASE_COST,
    CRITICAL_SELL_PENALTY_PRODUCTS,
    CRITICAL_SELL_RISK_FLOOR,
    CROP_FIRST_YIELD_DAY,
    CROP_SEED_COST,
    FEED_CRITICAL_THRESHOLD,
    FEED_LIMITED_THRESHOLD,
    FERTILIZER_CRITICAL_THRESHOLD,
    FERTILIZER_LIMITED_THRESHOLD,
    RESERVE_RATIO,
    SEED_CRITICAL_THRESHOLD,
    SEED_LIMITED_THRESHOLD,
)
from .models import BudgetAnalysis, EconomyProposal
from .rules import is_time_feasible, resource_level


def analyze_budget(state, reserve_ratio: float = RESERVE_RATIO) -> BudgetAnalysis:
    """
    Analyse du budget (spec section 9-11) : distingue la trésorerie totale
    du budget réellement engageable, en conservant une réserve de sécurité.
    """
    money = state.resources.money
    reserve = money * reserve_ratio
    safe_budget = max(0.0, money - reserve)
    return BudgetAnalysis(money=money, reserve=reserve, safe_budget=safe_budget)


def analyze_resources(state) -> Dict[str, str]:
    """
    Analyse des ressources (spec section 12-13). Retourne un niveau par
    ressource suivie : une graine par type possédé (`SEED_<TYPE>`), le
    stock de blé utilisé pour nourrir les animaux (`WHEAT`), et le
    fertilisant (`FERTILIZER`). N'invente aucune ressource non présente
    dans `FarmState`.
    """
    levels: Dict[str, str] = {}

    for crop_type, quantity in state.resources.seeds.items():
        levels[f"SEED_{crop_type}"] = resource_level(quantity, SEED_CRITICAL_THRESHOLD, SEED_LIMITED_THRESHOLD)

    wheat_quantity = state.resources.shed.get("WHEAT", 0)
    levels["WHEAT"] = resource_level(wheat_quantity, FEED_CRITICAL_THRESHOLD, FEED_LIMITED_THRESHOLD)

    fertilizer_quantity = state.resources.shed.get("FERTILIZER", 0)
    levels["FERTILIZER"] = resource_level(
        fertilizer_quantity, FERTILIZER_CRITICAL_THRESHOLD, FERTILIZER_LIMITED_THRESHOLD,
    )

    return levels


def _gross_revenue_from_net_expected_value(net_expected_value: float, cost: float) -> float:
    """
    Correction (revue d'archive, section 7/23-25) : pour PLANT (CropAgent),
    EXPANSION_OPPORTUNITY (AnimalAgent) et PRODUCE (MarketAgent), le champ
    `expected_value` de la proposition source est DÉJÀ un profit net
    (revenu potentiel - coût), pas un revenu brut :

        CropAgent.find_plant_tasks:
            expected_value = max_yield * price - seed_cost

        AnimalAgent.find_expansion_opportunities / scoring.estimate_expansion_value:
            expected_value = max_held * price - purchase_cost

        MarketAgent (PRODUCE) : reprend le même expected_value que PLANT.

    `_build_proposal` calcule ensuite `profit = revenue - cost`
    (scoring.calculate_profitability). Si on lui passait `expected_value`
    tel quel comme `revenue`, le coût serait soustrait une seconde fois,
    et `expected_profit` sous-estimerait systématiquement le profit réel
    de `cost` (ex: PLANT MELON — expected_value=1420, cost=80 -> profit
    calculé à tort à 1340 au lieu de 1420).

    Cette fonction reconstruit un revenu brut cohérent : en lui
    resoustrayant `cost` plus loin, `_build_proposal` retrouve exactement
    `net_expected_value` comme `expected_profit`, tout en gardant `cost`
    intact pour le calcul du risque, du ROI et du cash_delta.
    """
    return net_expected_value + cost


def _build_proposal(
    action: str, source_agent: str, target, product: Optional[str],
    cost: float, revenue: float, urgency: float, confidence: float,
    remaining_days: int, required_days: Optional[int], safe_budget: float,
    reason: str, quantity: float = 1.0, risk_floor: float = 0.0,
    dependencies: Sequence[str] = (),
) -> EconomyProposal:
    profit = scoring.calculate_profitability(revenue, cost)
    roi = scoring.calculate_roi(profit, cost)
    cash_delta = scoring.calculate_cash_delta(revenue, cost)
    risk = max(scoring.calculate_risk(cost, safe_budget), risk_floor)
    resource_efficiency = scoring.calculate_resource_efficiency(profit, cost, quantity)
    time_feasible = is_time_feasible(remaining_days, required_days)
    economic_score = scoring.calculate_economic_score(
        profit, roi, cash_delta, risk, urgency, resource_efficiency, time_feasible,
    )

    return EconomyProposal(
        agent="economy", action=action, source_agent=source_agent, target=target, product=product,
        cost=cost, expected_revenue=revenue, expected_profit=profit, roi=roi, cash_delta=cash_delta,
        risk=risk, urgency=urgency, resource_efficiency=resource_efficiency, economic_score=economic_score,
        reason=reason, confidence=confidence, quantity=float(max(1.0, quantity)), dependencies=tuple(dependencies),
    )


def evaluate_investment_proposals(state, investment_proposals, budget: BudgetAnalysis) -> List[EconomyProposal]:
    """Convertit les intentions de l'InvestmentAgent en EconomyProposal exécutables."""
    proposals = []
    remaining_days = state.time.remaining_days
    for ip in investment_proposals:
        cost = float(ip.cost)
        revenue = float(ip.expected_revenue)
        required_days = None
        if ip.action == "BUY_SEED" and ip.product in CROP_FIRST_YIELD_DAY:
            required_days = CROP_FIRST_YIELD_DAY[ip.product]
        if ip.action == "BUY_ANIMAL" and ip.product in ANIMAL_FIRST_YIELD_DAY:
            required_days = ANIMAL_FIRST_YIELD_DAY[ip.product]
        proposals.append(_build_proposal(
            action=ip.action, source_agent="investment", target=ip.target, product=ip.product,
            cost=cost, revenue=revenue, urgency=ip.urgency, confidence=ip.confidence,
            remaining_days=remaining_days, required_days=required_days, safe_budget=budget.safe_budget,
            reason=ip.reason, quantity=float(max(1, ip.quantity)),
            dependencies=ip.dependencies,
        ))
    return proposals


def evaluate_crop_proposals(state, crop_proposals, budget: BudgetAnalysis) -> List[EconomyProposal]:
    """
    Évalue chaque CropProposal indépendamment. Seule l'action PLANT engage
    une dépense connue (coût de la graine, spec section 9 table Object
    Types) ; HARVEST/WATER/FERTILIZE n'ont pas de coût monétaire direct
    documenté à ce niveau (déjà pris en compte dans expected_value par le
    CropAgent lui-même).
    """
    proposals = []
    remaining_days = state.time.remaining_days

    buy_seed_keys = {
        cp.crop_type: f"crop:BUY_SEED:None"
        for cp in crop_proposals
        if cp.action == "BUY_SEED" and cp.crop_type
    }

    for cp in crop_proposals:
        is_plant = cp.action == "PLANT"
        is_buy_seed = cp.action == "BUY_SEED"
        cost = (CROP_SEED_COST.get(cp.crop_type, 0.0) * float(getattr(cp, "quantity", 1.0))) if is_buy_seed else (CROP_SEED_COST.get(cp.crop_type, 0.0) if is_plant else 0.0)
        required_days = CROP_FIRST_YIELD_DAY.get(cp.crop_type) if cp.action in {"PLANT", "BUY_SEED"} else None
        # PLANT : cp.expected_value est déjà net du coût de la graine
        # (CropAgent.find_plant_tasks) -> reconstruire un revenu brut pour
        # éviter de soustraire `cost` une seconde fois (voir helper ci-dessus).
        revenue = (
            float(cp.expected_value) if is_buy_seed else
            (_gross_revenue_from_net_expected_value(cp.expected_value, cost) if is_plant else cp.expected_value)
        )

        dependencies = ()
        # Si un achat de graines du même cycle existe, PLANT doit attendre
        # cet approvisionnement. Sans cette relation le Planner peut placer
        # BUY_SEED et PLANT au même niveau et le Critic ne peut pas savoir que
        # la graine achetée couvre la consommation future.
        if is_plant and cp.crop_type in buy_seed_keys and int(state.resources.seeds.get(cp.crop_type, 0)) <= 0:
            dependencies = (buy_seed_keys[cp.crop_type],)

        proposals.append(_build_proposal(
            action=cp.action, source_agent="crop", target=cp.target, product=cp.crop_type,
            cost=cost, revenue=revenue, urgency=cp.urgency, confidence=cp.confidence,
            remaining_days=remaining_days, required_days=required_days, safe_budget=budget.safe_budget,
            reason=f"{cp.action} {cp.crop_type or ''} : {cp.reason}".strip(),
            quantity=float(max(1.0, getattr(cp, "quantity", 1.0))),
            dependencies=dependencies,
        ))
    return proposals


def evaluate_animal_proposals(state, animal_proposals, budget: BudgetAnalysis) -> List[EconomyProposal]:
    """
    Évalue chaque AnimalProposal indépendamment. Seule EXPANSION_OPPORTUNITY
    engage une dépense connue (coût d'achat de l'animal) ; FEED/CARE/
    HARVEST/COLLECT_FERTILIZER n'ont pas de coût monétaire direct
    documenté à ce niveau.
    """
    proposals = []
    remaining_days = state.time.remaining_days

    for ap in animal_proposals:
        is_expansion = ap.action == "EXPANSION_OPPORTUNITY"
        is_buy_animal = ap.action == "BUY_ANIMAL"
        cost = (ANIMAL_PURCHASE_COST.get(ap.animal_type, 0.0) * float(getattr(ap, "quantity", 1.0))) if is_buy_animal else (ANIMAL_PURCHASE_COST.get(ap.animal_type, 0.0) if is_expansion else 0.0)
        required_days = ANIMAL_FIRST_YIELD_DAY.get(ap.animal_type) if ap.action in {"EXPANSION_OPPORTUNITY", "BUY_ANIMAL"} else None
        # EXPANSION_OPPORTUNITY : ap.expected_value est déjà net du coût
        # d'achat (AnimalAgent.scoring.estimate_expansion_value) -> même
        # correction que pour PLANT ci-dessus.
        revenue = (
            float(ap.expected_value) if is_buy_animal else
            (_gross_revenue_from_net_expected_value(ap.expected_value, cost) if is_expansion else ap.expected_value)
        )

        dependencies = []
        if ap.action in {"BUILD_COOP", "BUILD_PASTURE"} and ap.target in set(getattr(state.crops, "weed_tiles", ())):
            dependencies.append(f"crop:DUG:{ap.target}")
        if ap.action == "PICKUP" and ap.animal_type:
            # L'animal doit être physiquement dans l'inventaire du worker
            # avant PLACE. S'il vient d'être acheté ce tour, BUY_ANIMAL est
            # la dépendance; sinon le stock du shed suffit.
            if int(state.resources.shed.get(ap.animal_type, 0)) <= 0:
                dependencies.append(f"animal:BUY_ANIMAL:None:{ap.animal_type}")
        if ap.action == "PLACE" and ap.animal_type:
            if int(state.resources.shed.get(ap.animal_type, 0)) <= 0:
                dependencies.append(f"animal:BUY_ANIMAL:None:{ap.animal_type}")
            else:
                # Le PICKUP explicite est nécessaire quand l'animal est dans
                # le shed. Il est résolu si AnimalAgent l'a proposé ce tour.
                center = state.land.board_size // 2
                pickup_candidates = {(center-1, center-1), (center, center-1),
                                    (center-1, center), (center, center)}
                pickup_target = next((p for p in pickup_candidates if any(
                    q.action == "PICKUP" and q.animal_type == ap.animal_type and q.target == p
                    for q in animal_proposals
                )), None)
                if pickup_target is not None:
                    dependencies.append(f"animal:PICKUP:{pickup_target}:{ap.animal_type}")
            empty_structures = {pos for pos, _ in state.animals.empty_structures}
            if ap.target not in empty_structures:
                build_action = "BUILD_COOP" if ap.animal_type == "GOOSE" else "BUILD_PASTURE"
                dependencies.append(f"animal:{build_action}:{ap.target}:{ap.animal_type}")
        proposals.append(_build_proposal(
            action=ap.action, source_agent="animal", target=ap.target, product=ap.animal_type,
            cost=cost, revenue=revenue, urgency=ap.urgency, confidence=ap.confidence,
            remaining_days=remaining_days, required_days=required_days, safe_budget=budget.safe_budget,
            reason=f"{ap.action} {ap.animal_type or ''} : {ap.reason}".strip(),
            quantity=float(max(1.0, getattr(ap, "quantity", 1.0))), dependencies=tuple(dependencies),
        ))
    return proposals


def _find_harvest_dependencies(product: str, crop_proposals, animal_proposals) -> List[str]:
    """
    Relie une vente (MarketProposal SELL) aux récoltes qui produiraient ce
    même produit, pour signaler au futur PlannerAgent de ne pas compter ce
    revenu deux fois indépendamment (spec section 54-55).
    """
    dependencies = []
    for cp in crop_proposals:
        if cp.action == "HARVEST" and cp.crop_type == product:
            dependencies.append(f"crop:HARVEST:{cp.target}")
    for ap in animal_proposals:
        if ap.action == "HARVEST" and ANIMAL_PRODUCT.get(ap.animal_type) == product:
            dependencies.append(f"animal:HARVEST:{ap.target}")
    return dependencies


def evaluate_market_proposals(
    state, market_proposals, budget: BudgetAnalysis, resource_levels: Dict[str, str],
    crop_proposals=(), animal_proposals=(),
) -> List[EconomyProposal]:
    """
    Évalue chaque MarketProposal indépendamment :
    - SELL  : revenu immédiat, pas de coût direct, mais pénalisé si le
      produit vendu est une ressource actuellement CRITICAL pour la ferme
      (spec section 13 : ne pas aggraver une pénurie de WHEAT/FERTILIZER).
    - HOLD  : aucun mouvement de trésorerie immédiat (proposition
      informationnelle, spec section 14) ; economic_score reste bas.
    - PRODUCE : traité comme une opportunité de plantation future, donc
      évalué avec le même coût de graine documenté que CropAgent.PLANT.
    """
    proposals = []
    remaining_days = state.time.remaining_days

    for mp in market_proposals:
        quantity = mp.quantity if mp.quantity else 1.0

        if mp.action == "SELL":
            cost = 0.0
            revenue = mp.expected_value
            required_days = None
            risk_floor = (
                CRITICAL_SELL_RISK_FLOOR
                if mp.product in CRITICAL_SELL_PENALTY_PRODUCTS and resource_levels.get(mp.product) == "CRITICAL"
                else 0.0
            )
            dependencies = _find_harvest_dependencies(mp.product, crop_proposals, animal_proposals)
            reason = f"SELL {mp.product} : {mp.reason}"
            if risk_floor > 0:
                reason += " ; attention : réserve de cette ressource actuellement critique"

        elif mp.action == "HOLD":
            cost = 0.0
            revenue = 0.0  # pas de réalisation immédiate : aucun impact sur la trésorerie actuelle
            required_days = None
            risk_floor = 0.0
            dependencies = ()
            reason = f"HOLD {mp.product} : {mp.reason} (valeur non réalisée si vendu maintenant : {mp.expected_value:.0f})"

        else:  # PRODUCE
            cost = CROP_SEED_COST.get(mp.product, 0.0)
            # PRODUCE reprend le même expected_value (déjà net du coût de
            # graine) que CropAgent.PLANT -> même correction.
            revenue = _gross_revenue_from_net_expected_value(mp.expected_value, cost)
            required_days = CROP_FIRST_YIELD_DAY.get(mp.product)
            risk_floor = 0.0
            dependencies = ()
            reason = f"PRODUCE {mp.product} : {mp.reason}"

        proposals.append(_build_proposal(
            action=mp.action, source_agent="market", target=None, product=mp.product,
            cost=cost, revenue=revenue, urgency=mp.urgency, confidence=mp.confidence,
            remaining_days=remaining_days, required_days=required_days, safe_budget=budget.safe_budget,
            reason=reason, quantity=quantity, risk_floor=risk_floor, dependencies=dependencies,
        ))
    return proposals