"""
agent.py — PlannerAgent, point d'entrée public du module.

API publique :

    planner = PlannerAgent()
    plan = planner.plan(state, economy_proposals)   # -> Plan

PlannerAgent lit uniquement FarmState et les EconomyProposal déjà produites
par EconomyAgent (jamais `obs` directement, jamais d'appel direct aux
agents précédents ni à leurs modules internes, spec section 68). Il ne
modifie ni FarmState ni les propositions reçues, et n'exécute AUCUNE action
Kaggriculture : seulement un Plan, consommé plus tard par un futur
CriticAgent / CoordinatorAgent / ExecutorAgent (hors scope ici).

Algorithme (spec section 46), sélection gloutonne (section 47-48) :

    1. dédoublonner les propositions (PLANT vs PRODUCE, même opportunité)
    2. résoudre les conflits de cible (deux propositions, une case)
    3. filtrer les propositions statiquement infaisables
    4. construire le graphe de dépendances, détecter et exclure les cycles
    5. tant qu'il reste des propositions "prêtes" (dépendances satisfaites) :
       a. trier par priorité (economic_score, urgency, risk)
       b. prendre la meilleure, vérifier ressources/budget/workers
       c. si compatible : l'accepter, mettre à jour les ledgers, continuer
       d. sinon : l'écarter (contrainte non satisfaite), continuer
    6. tout ce qui reste bloqué par une dépendance rejetée est écarté
    7. calculer le score, le profit net, la confiance, l'explication
"""

from typing import Dict, List, Tuple

from . import conflicts, dependencies, rules, scoring
from .analyzers import analyze_constraints
from .constants import WORKER_REQUIRED_ACTIONS
from .whatif import evaluate_plan
from ..economy.strategic import build_strategic_economy
from .models import Plan, PlanStep, RejectedProposal


class PlannerAgent:
    """Agent de synthèse finale : sélectionne et ordonne un plan d'actions cohérent."""

    def plan(self, state, economy_proposals) -> Plan:
        # HOLD is an information signal, not an executable plan step. Drop it
        # before the rejection ledger so benign "do nothing" recommendations
        # do not inflate planner-rejection metrics or compete with real work.
        proposals = [p for p in economy_proposals if getattr(p, "action", None) != "HOLD"]
        if not proposals:
            return Plan()

        rejected: List[RejectedProposal] = []

        proposals, dedup_rejected = conflicts.deduplicate_proposals(proposals)
        rejected += dedup_rejected

        proposals, conflict_rejected = conflicts.resolve_target_conflicts(proposals)
        rejected += conflict_rejected

        proposals, infeasible_rejected = self._filter_feasible(proposals, state)
        rejected += infeasible_rejected

        proposals, cycle_rejected = self._remove_cycles(proposals)
        rejected += cycle_rejected

        constraints = analyze_constraints(state)
        graph = dependencies.resolve_dependencies(proposals)
        by_id = {dependencies.proposal_id(ep): ep for ep in proposals}

        steps, accepted_proposals, scheduling_rejected = self._schedule(
            proposals, graph, by_id, constraints,
        )
        rejected += scheduling_rejected

        plan = self._build_plan(steps, accepted_proposals, rejected)
        strategic = build_strategic_economy(state)
        wi = evaluate_plan(plan, state)
        return Plan(steps=plan.steps, total_score=max(0.0, min(1.0, plan.total_score + 0.08 * (wi["expected"] / max(1.0, abs(plan.expected_profit)+1.0)))),
                    total_cost=plan.total_cost, expected_profit=plan.expected_profit, confidence=plan.confidence,
                    explanation=plan.explanation + f" What-if: worst={wi['worst']:.0f}$ expected={wi['expected']:.0f}$ best={wi['best']:.0f}$.",
                    rejected=plan.rejected, terminal_value=strategic.terminal_wealth + wi['expected'],
                    risk_budget=strategic.risk_budget, what_if_score=max(0.0, min(1.0, 0.5 + wi['worst']/max(1.0, abs(plan.expected_profit)+1.0)*0.5)))

    # ------------------------------------------------------------------ #
    # Étape 3 : faisabilité statique
    # ------------------------------------------------------------------ #
    @staticmethod
    def _filter_feasible(proposals, state) -> Tuple[List, List[RejectedProposal]]:
        feasible: List = []
        rejected: List[RejectedProposal] = []
        for ep in proposals:
            reason = rules.is_feasible(ep, state, proposals)
            if reason is None:
                feasible.append(ep)
            else:
                rejected.append(RejectedProposal(
                    proposal_id=dependencies.proposal_id(ep), action=ep.action, source_agent=ep.source_agent,
                    target=ep.target, product=ep.product, reason=reason,
                ))
        return feasible, rejected

    # ------------------------------------------------------------------ #
    # Étape 4 : cycles
    # ------------------------------------------------------------------ #
    @staticmethod
    def _remove_cycles(proposals) -> Tuple[List, List[RejectedProposal]]:
        graph = dependencies.resolve_dependencies(proposals)
        cyclic_ids = dependencies.detect_cycles(graph)
        if not cyclic_ids:
            return proposals, []

        by_id = {dependencies.proposal_id(ep): ep for ep in proposals}
        rejected = [
            RejectedProposal(
                proposal_id=pid, action=by_id[pid].action, source_agent=by_id[pid].source_agent,
                target=by_id[pid].target, product=by_id[pid].product,
                reason="cycle de dépendances détecté : proposition exclue du plan (spec section 14)",
            )
            for pid in sorted(cyclic_ids)
        ]
        remaining = [ep for ep in proposals if dependencies.proposal_id(ep) not in cyclic_ids]
        return remaining, rejected

    # ------------------------------------------------------------------ #
    # Étape 5 : sélection gloutonne sous contraintes
    # ------------------------------------------------------------------ #
    @staticmethod
    def _dependencies_satisfied(pid: str, graph: Dict[str, Tuple[str, ...]], accepted_ids: set) -> bool:
        deps = graph.get(pid, ())
        if not deps:
            return True
        # Si plusieurs propositions candidates partagent la même clé de
        # dépendance courte (ex: deux HARVEST possibles sur la même case),
        # il suffit qu'UNE d'entre elles soit retenue (voir
        # dependencies.resolve_dependencies).
        return all(dep in accepted_ids for dep in deps)

    def _schedule(self, proposals, graph, by_id, constraints):
        resource_ledger = constraints.resource_ledger
        budget_ledger = constraints.budget_ledger
        num_workers = constraints.num_workers

        remaining_ids = set(by_id.keys())
        accepted_ids: List[str] = []
        accepted_phase: Dict[str, int] = {}
        phase_worker_usage: Dict[int, int] = {}
        steps: List[PlanStep] = []
        accepted_proposals: List = []
        rejected: List[RejectedProposal] = []

        while remaining_ids:
            ready_ids = [
                pid for pid in remaining_ids
                if self._dependencies_satisfied(pid, graph, set(accepted_ids))
            ]
            if not ready_ids:
                break  # tout ce qui reste est bloqué par une dépendance jamais retenue

            ready_ids.sort(key=lambda pid: (
                -float(by_id[pid].economic_score),
                -float(by_id[pid].urgency),
                float(by_id[pid].risk),
                -float(by_id[pid].expected_profit),
                str(by_id[pid].action),
                str(by_id[pid].product),
                str(by_id[pid].target),
                pid,
            ))

            placed_this_round = False
            for pid in ready_ids:
                ep = by_id[pid]
                deps = graph.get(pid, ())
                required_phase = 0 if not deps else 1 + max(
                    accepted_phase[d] for d in deps if d in accepted_phase
                )
                worker_required = ep.action in WORKER_REQUIRED_ACTIONS

                target_phase = self._find_phase(required_phase, worker_required, num_workers, phase_worker_usage)
                if target_phase is None:
                    continue  # pas de créneau worker trouvable dans une limite raisonnable
                if not resource_ledger.can_afford(ep) or not budget_ledger.can_afford(ep):
                    continue

                resource_ledger.consume(ep)
                budget_ledger.apply(ep)
                if worker_required:
                    phase_worker_usage[target_phase] = phase_worker_usage.get(target_phase, 0) + 1

                accepted_ids.append(pid)
                accepted_phase[pid] = target_phase
                accepted_proposals.append(ep)
                steps.append(self._build_step(ep, pid, target_phase, deps, worker_required))
                remaining_ids.discard(pid)
                placed_this_round = True
                break  # un seul step accepté par itération (spec section 47 : glouton pas-à-pas)

            if not placed_this_round:
                # Rien parmi les "prêts" ne peut être casé maintenant (ressource,
                # budget ou worker insuffisant) : on les écarte définitivement
                # plutôt que de boucler indéfiniment.
                for pid in ready_ids:
                    ep = by_id[pid]
                    rejected.append(RejectedProposal(
                        proposal_id=pid, action=ep.action, source_agent=ep.source_agent,
                        target=ep.target, product=ep.product,
                        reason="ressource, budget sécurisé ou créneau worker insuffisant pour ce plan",
                    ))
                    remaining_ids.discard(pid)

        for pid in remaining_ids:
            ep = by_id[pid]
            rejected.append(RejectedProposal(
                proposal_id=pid, action=ep.action, source_agent=ep.source_agent,
                target=ep.target, product=ep.product,
                reason="dépendance requise jamais retenue dans le plan",
            ))

        return steps, accepted_proposals, rejected

    @staticmethod
    def _find_phase(required_phase: int, worker_required: bool, num_workers: int,
                     phase_worker_usage: Dict[int, int]) -> "int | None":
        if not worker_required:
            return required_phase
        if num_workers <= 0:
            return None
        phase = required_phase
        max_phase_search = required_phase + 200  # borne défensive (nombre de propositions toujours petit)
        while phase <= max_phase_search:
            if phase_worker_usage.get(phase, 0) < num_workers:
                return phase
            phase += 1
        return None

    @staticmethod
    def _build_step(ep, pid: str, phase: int, deps: Tuple[str, ...], worker_required: bool) -> PlanStep:
        return PlanStep(
            step_id=pid, action=ep.action, source_agent=ep.source_agent, target=ep.target, product=ep.product,
            phase=phase, priority=ep.economic_score, estimated_cost=ep.cost,
            expected_revenue=ep.expected_revenue, expected_profit=ep.expected_profit,
            worker_required=worker_required, worker_id=None,
            depends_on=deps, reason=ep.reason, quantity=getattr(ep, "quantity", 1.0), confidence=ep.confidence,
        )

    # ------------------------------------------------------------------ #
    # Étape 7 : score, profit net, confiance, explication
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_plan(steps: List[PlanStep], accepted_proposals: List, rejected: List[RejectedProposal]) -> Plan:
        steps = tuple(sorted(steps, key=lambda s: (s.phase, s.step_id)))
        total_cost = sum(step.estimated_cost for step in steps)
        net_profit = scoring.calculate_net_expected_profit(steps)
        avg_urgency = scoring.calculate_urgency_score(accepted_proposals)
        avg_risk = scoring.calculate_avg_risk(accepted_proposals)
        total_score = scoring.calculate_plan_score(net_profit, avg_urgency, avg_risk)
        confidence = scoring.calculate_plan_confidence(steps, len(rejected))
        explanation = PlannerAgent._explain(steps, rejected, net_profit)

        provisional = Plan(
            steps=steps, total_score=total_score, total_cost=total_cost,
            expected_profit=net_profit, confidence=confidence,
            explanation=explanation, rejected=tuple(rejected),
        )
        return provisional

    @staticmethod
    def _explain(steps: Tuple[PlanStep, ...], rejected: List[RejectedProposal], net_profit: float) -> str:
        if not steps:
            if rejected:
                return f"Aucune proposition retenue ({len(rejected)} écartée(s) : ressources, budget ou dépendances insuffisants)."
            return "Aucune proposition économique reçue."

        num_phases = max(step.phase for step in steps) + 1
        lines = [
            f"{len(steps)} action(s) retenue(s) sur {num_phases} phase(s), valeur nette attendue "
            f"{net_profit:.0f}$ (dépendances déjà déduites du double comptage)."
        ]
        for phase in range(num_phases):
            phase_steps = [s for s in steps if s.phase == phase]
            actions = ", ".join(f"{s.action} {s.product or ''}".strip() for s in phase_steps)
            lines.append(f"Phase {phase} : {actions}")
        if rejected:
            lines.append(f"{len(rejected)} proposition(s) écartée(s) (voir Plan.rejected pour le détail).")
        return " ".join(lines)