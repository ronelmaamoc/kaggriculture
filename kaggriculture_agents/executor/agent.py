"""
agent.py — ExecutorAgent, point d'entrée public du module.

API publique :

    executor = ExecutorAgent()                      # créé UNE FOIS, réutilisé à chaque tour
    result = executor.execute(state, schedule)       # -> ExecutionResult
    result = executor.execute(state, schedule, dry_run=True)   # simulation, rien envoyé

CONTRAINTE RÉELLE (voir constants.py, "DÉCOUVERTE IMPORTANTE") :
Kaggriculture ne fournit qu'UN SEUL point d'entrée, `agent(obs) -> dict`,
appelé une fois par tour. Un `ExecutionSchedule` peut couvrir plusieurs
phases (plusieurs tours futurs, voir kaggriculture_agents/coordinator/README.md, "1
phase = 1 tour"), mais un seul appel à `execute()` ne peut agir QUE sur le
tour courant (`state.time.step`) : les steps programmés pour des tours
ultérieurs sont marqués `SkippedStep(reason=FUTURE_TURN)`, pas exécutés ni
en erreur -- le pipeline complet est rejoué à chaque tour (nouvelle
observation -> nouveau Plan -> nouveau Schedule), donc ces steps seront
reproposés naturellement le moment venu.

Algorithme (spec section 33, adapté à cette contrainte) :

    1. schedule vide ou BLOCKED -> court-circuit
    2. idempotence : rejouer un schedule déjà traité (mêmes execution_id,
       même appel non-dry_run) ne renvoie rien une deuxième fois, sauf
       `force=True` (spec section 26)
    3. isoler les steps dus CE tour (estimated_turn == state.time.step) ;
       les autres -> SkippedStep(FUTURE_TURN)
    4. execution_engine.run(...) sur les steps dus
    5. assembler `turn_actions` (farmer / hands / market)
    6. déterminer ExecutionStatus, construire ExecutionResult
"""

from typing import FrozenSet, Optional, Set

from . import execution_engine
from .constants import (
    BLOCKED_SCHEDULE_STATUS_VALUE,
    DEFAULT_TURN_ACTIONS,
    REASON_ALREADY_EXECUTED,
    REASON_FUTURE_TURN,
)
from .environment_adapter import EnvironmentAdapter, QueueingEnvironmentAdapter
from .logger import ExecutionLogger
from .models import ExecutionResult, ExecutionStatus, SkippedStep


class ExecutorAgent:
    """Transforme un ExecutionSchedule (dû ce tour) en actions Kaggriculture réellement soumises."""

    def __init__(self, adapter: Optional[EnvironmentAdapter] = None):
        self._default_adapter = adapter or QueueingEnvironmentAdapter()
        self._completed_batches: Set[FrozenSet[str]] = set()

    def reset(self) -> None:
        """Réinitialise la mémoire d'exécution au début d'une nouvelle partie."""
        self._completed_batches.clear()

    def execute(
        self, state, schedule, adapter: Optional[EnvironmentAdapter] = None,
        dry_run: bool = False, force: bool = False, log: bool = False,
    ) -> ExecutionResult:
        active_adapter = adapter or self._default_adapter
        logger = ExecutionLogger(emit=log)

        if not schedule.steps:
            return ExecutionResult(
                status=ExecutionStatus.COMPLETED,
                turn_actions=dict(DEFAULT_TURN_ACTIONS),
                explanation="Schedule vide : rien à exécuter.",
            )

        if schedule.status.value == BLOCKED_SCHEDULE_STATUS_VALUE:
            return ExecutionResult(
                status=ExecutionStatus.BLOCKED,
                turn_actions=dict(DEFAULT_TURN_ACTIONS),
                explanation=f"Schedule bloqué en amont : {schedule.explanation}",
            )

        current_turn = state.time.step
        batch_signature = frozenset((step.execution_id, step.estimated_turn, current_turn) for step in schedule.steps)
        if not dry_run and not force and batch_signature in self._completed_batches:
            skipped = tuple(
                SkippedStep(step.execution_id, step.plan_step_id, REASON_ALREADY_EXECUTED)
                for step in schedule.steps
            )
            return ExecutionResult(
                status=ExecutionStatus.COMPLETED,
                skipped_steps=skipped,
                turn_actions=dict(DEFAULT_TURN_ACTIONS),
                explanation="Ce schedule a déjà été exécuté (mêmes execution_id) ; "
                            "aucune action renvoyée une deuxième fois (utiliser force=True pour outrepasser).",
            )

        due_steps = [s for s in schedule.steps if s.estimated_turn == current_turn]
        future_steps = [s for s in schedule.steps if s.estimated_turn != current_turn]

        logger.execution_start(f"exec-batch:{current_turn}", len(due_steps))

        executed, failed, skipped_from_engine, worker_actions, market_orders = execution_engine.run(
            due_steps, state, active_adapter, dry_run, logger,
        )

        future_skipped = tuple(
            SkippedStep(s.execution_id, s.plan_step_id, REASON_FUTURE_TURN) for s in future_steps
        )
        skipped_steps = tuple(skipped_from_engine) + future_skipped

        status = self._determine_status(executed, failed, due_steps)
        logger.execution_end(f"exec-batch:{current_turn}", status.value)

        turn_actions = self._assemble_turn_actions(state, worker_actions, market_orders)

        if not dry_run:
            self._completed_batches.add(batch_signature)

        explanation = self._explain(status, executed, failed, skipped_steps, dry_run)

        return ExecutionResult(
            status=status,
            executed_steps=tuple(executed),
            failed_steps=tuple(failed),
            skipped_steps=skipped_steps,
            actions_sent=len(due_steps),
            actions_succeeded=len(executed),
            actions_failed=len(failed),
            turn_actions=turn_actions,
            explanation=explanation,
        )

    @staticmethod
    def _assemble_turn_actions(state, worker_actions, market_orders) -> dict:
        farmer = state.workers.farmer
        farmer_action = worker_actions.get(farmer.worker_id, ["PASS"]) if farmer else ["PASS"]
        hands_actions = [worker_actions.get(hand.worker_id, ["PASS"]) for hand in state.workers.hands]
        priority = {
            "SELL": 0, "BUY_SEED": 1, "BUY_PRODUCT": 2, "BUY_ANIMAL": 3,
            "HIRE": 4, "BUY_LAND": 5,
        }
        market_orders = sorted(market_orders, key=lambda o: (priority.get(o[0], 99), str(o)))
        return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}

    @staticmethod
    def _determine_status(executed, failed, due_steps) -> ExecutionStatus:
        if any(not f.recoverable for f in failed):
            return ExecutionStatus.FAILED
        if not due_steps:
            return ExecutionStatus.COMPLETED
        if failed and executed:
            return ExecutionStatus.PARTIAL
        if failed and not executed:
            return ExecutionStatus.FAILED
        return ExecutionStatus.COMPLETED

    @staticmethod
    def _explain(status: ExecutionStatus, executed, failed, skipped_steps, dry_run: bool) -> str:
        prefix = "[dry_run] " if dry_run else ""
        base = f"{prefix}{len(executed)} action(s) exécutée(s), {len(failed)} échec(s), " \
               f"{len(skipped_steps)} étape(s) ignorée(s) (statut {status.value})."
        if failed:
            base += " Échecs : " + "; ".join(f"{f.plan_step_id} ({f.code})" for f in failed) + "."
        return base
