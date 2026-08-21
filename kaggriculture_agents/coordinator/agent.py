"""
agent.py — CoordinatorAgent, point d'entrée public du module.

API publique :

    coordinator = CoordinatorAgent()
    schedule = coordinator.coordinate(state, plan, critique)   # -> ExecutionSchedule

CoordinatorAgent lit uniquement FarmState, le Plan déjà produit par
PlannerAgent et la Critique déjà produite par CriticAgent (jamais `obs`
directement, jamais d'appel aux agents précédents ni à leurs modules
internes -- accès en pur duck-typing, voir constants.py). Il ne modifie ni
FarmState, ni Plan, ni Critique, et n'exécute AUCUNE action Kaggriculture :
seulement un ExecutionSchedule, destiné à un futur ExecutorAgent (hors
scope ici).

Algorithme (spec section 30, simplifié car phases/dépendances/capacité
workers sont déjà validées en amont par Planner+Critic -- voir README.md) :

    1. plan.steps vide -> court-circuit : READY, schedule vide
    2. critique.status != APPROVED -> court-circuit : BLOCKED (spec section 5)
    3. scheduler.schedule(...) : dépendances, workers, conflits, datation
    4. déterminer le statut final (validators.py) et l'explication
    5. produire l'ExecutionSchedule
"""

from . import resource_scheduler, scheduler, validators
from .models import ExecutionSchedule, ScheduleStatus


class CoordinatorAgent:
    """Chef d'orchestre de l'exécution : transforme un Plan approuvé en ExecutionSchedule."""

    def coordinate(self, state, plan, critique) -> ExecutionSchedule:
        if not plan.steps:
            return ExecutionSchedule(
                steps=(), total_steps=0, estimated_turns=0,
                status=ScheduleStatus.READY,
                explanation="Plan vide : rien à coordonner.",
                blocked=(),
            )

        # Le Critic peut fournir un plan révisé. Le Coordinator doit coordonner
        # cette proposition plutôt que de revenir au plan initial.
        effective_plan = getattr(critique, "revised_plan", None) or plan

        rejection_reason = validators.check_critique_approved(critique)
        if rejection_reason is not None:
            return ExecutionSchedule(
                steps=(), total_steps=0, estimated_turns=0,
                status=ScheduleStatus.BLOCKED,
                explanation=rejection_reason,
                blocked=(),
            )

        workers = [(w.worker_id, w.position) for w in state.workers.all_workers]
        execution_steps, blocked = scheduler.schedule(effective_plan.steps, workers, base_turn=state.time.step)

        status = validators.determine_status(len(effective_plan.steps), len(blocked))
        explanation = self._explain(status, execution_steps, blocked)
        estimated_turns = resource_scheduler.compute_estimated_turns(execution_steps)

        return ExecutionSchedule(
            steps=tuple(execution_steps),
            total_steps=len(execution_steps),
            estimated_turns=estimated_turns,
            status=status,
            explanation=explanation,
            blocked=tuple(blocked),
        )

    @staticmethod
    def _explain(status: ScheduleStatus, execution_steps, blocked) -> str:
        if status == ScheduleStatus.BLOCKED and not execution_steps:
            details = "; ".join(f"{b.plan_step_id} ({b.reason})" for b in blocked)
            return f"Aucune action du plan n'a pu être programmée : {details}." if details else \
                "Aucune action du plan n'a pu être programmée."

        num_phases = max(step.phase for step in execution_steps) + 1 if execution_steps else 0
        base = f"{len(execution_steps)} action(s) programmée(s) sur {num_phases} phase(s)."
        if blocked:
            base += f" {len(blocked)} action(s) bloquée(s) (voir ExecutionSchedule.blocked)."
        return base
