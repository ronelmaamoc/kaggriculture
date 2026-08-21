"""
execution_engine.py — Boucle principale d'exécution (spec sections 11, 33).

Prend la liste des `ExecutionStep` DUES ce tour (déjà filtrées par
agent.py — voir sa docstring pour la notion de "dû ce tour"), triées de
façon déterministe, et les exécute une par une :

    dépendances -> worker -> cible -> mapping -> adapter -> enregistrement

Ne construit ni ne modifie `ExecutionSchedule` : lit uniquement ses steps.
"""

from typing import Dict, List, Set, Tuple

from . import action_mapper, error_handler, validators
from .constants import (
    CODE_INVALID_ACTION,
    CODE_INVALID_TARGET,
    CODE_WORKER_UNAVAILABLE,
    MARKET_SELL_ACTION,
    REASON_DEPENDENCY_FAILED,
    REASON_ENGINE_STOPPED,
)
from .models import ExecutedStep, ExecutionFailure, SkippedStep


def run(due_steps, state, adapter, dry_run: bool, logger) -> Tuple[
    List[ExecutedStep], List[ExecutionFailure], List[SkippedStep], Dict[str, list], Dict[str, list],
]:
    """
    Retourne (executed, failed, skipped, worker_actions, market_orders).
    `worker_actions` : {worker_id: action_tuple} ; `market_orders` : liste
    d'ordres marché. agent.py les assemble ensuite en `turn_actions`.
    """
    executed: List[ExecutedStep] = []
    failed: List[ExecutionFailure] = []
    skipped: List[SkippedStep] = []
    worker_actions: Dict[str, list] = {}
    market_orders: List[list] = []

    failed_or_skipped_plan_ids: Set[str] = set()
    workers_used_this_turn: Set[str] = set()
    # Dynamic validation view: actions executed earlier in the same turn can
    # remove a crop/animal, so a one-time index is not sufficient.
    crop_index = validators.build_crop_index(state)
    animal_index = validators.build_animal_index(state)
    invalidated_targets: Set[Tuple[int, int]] = set()

    engine_stopped = False

    for step in sorted(due_steps, key=lambda s: s.execution_id):
        if engine_stopped:
            skipped.append(SkippedStep(step.execution_id, step.plan_step_id, REASON_ENGINE_STOPPED))
            logger.action_skipped(step.execution_id, REASON_ENGINE_STOPPED)
            continue

        blocking_dep = next((d for d in step.dependencies if d in failed_or_skipped_plan_ids), None)
        if blocking_dep is not None:
            skipped.append(SkippedStep(step.execution_id, step.plan_step_id, REASON_DEPENDENCY_FAILED))
            failed_or_skipped_plan_ids.add(step.plan_step_id)
            logger.action_skipped(step.execution_id, REASON_DEPENDENCY_FAILED)
            continue

        if step.action in {"SELL", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "HIRE", "BUY_LAND"}:
            outcome = action_mapper.map_market_order(step)
            worker_id_for_result = None
        else:
            worker_error = validators.check_worker_available(step, state, workers_used_this_turn)
            if worker_error is not None:
                failed.append(ExecutionFailure(
                    step.execution_id, step.plan_step_id, CODE_WORKER_UNAVAILABLE, worker_error, recoverable=True,
                ))
                failed_or_skipped_plan_ids.add(step.plan_step_id)
                logger.action_failure(step.execution_id, CODE_WORKER_UNAVAILABLE, worker_error)
                continue

            if step.target in invalidated_targets and step.action not in {"DIG", "DUG"}:
                target_error = f"La cible {step.target} a déjà été invalidée par une action réussie plus tôt ce tour."
            else:
                target_error = validators.check_target_exists(step, state, crop_index, animal_index)
            if target_error is not None:
                failed.append(ExecutionFailure(
                    step.execution_id, step.plan_step_id, CODE_INVALID_TARGET, target_error, recoverable=True,
                ))
                failed_or_skipped_plan_ids.add(step.plan_step_id)
                logger.action_failure(step.execution_id, CODE_INVALID_TARGET, target_error)
                continue

            workers_used_this_turn.add(step.worker_id)
            position = validators.worker_position(step, state)
            outcome = action_mapper.map_worker_action(step, position)
            worker_id_for_result = step.worker_id

        if not outcome.ok:
            failed.append(ExecutionFailure(
                step.execution_id, step.plan_step_id, outcome.error_code, outcome.error_message, recoverable=True,
            ))
            failed_or_skipped_plan_ids.add(step.plan_step_id)
            logger.action_failure(step.execution_id, outcome.error_code, outcome.error_message)
            continue

        logger.action_start(step.execution_id, outcome.action, worker_id_for_result)

        if dry_run:
            executed.append(ExecutedStep(
                step.execution_id, step.plan_step_id, outcome.action, worker_id_for_result,
                success=True, turn=None, result=None, product=step.product, target=step.target,
            ))
            logger.action_success(step.execution_id, None)
        else:
            result = adapter.execute_action(outcome.action, worker_id_for_result)
            if result.success:
                executed.append(ExecutedStep(
                    step.execution_id, step.plan_step_id, outcome.action, worker_id_for_result,
                    success=True, turn=result.turn, result=result, product=step.product, target=step.target,
                ))
                logger.action_success(step.execution_id, result.turn)
                if step.target is not None and step.action == "HARVEST":
                    crop_index.pop(step.target, None)
                    animal_index.pop(step.target, None)
                    invalidated_targets.add(step.target)
                elif step.target is not None and step.action in {"DIG", "DUG"}:
                    crop_index.pop(step.target, None)
                    invalidated_targets.add(step.target)
            else:
                code = result.error_code or CODE_INVALID_ACTION
                message = result.message or "Action refusée par l'environnement."
                recoverable = error_handler.is_recoverable(code)
                failed.append(ExecutionFailure(step.execution_id, step.plan_step_id, code, message, recoverable))
                failed_or_skipped_plan_ids.add(step.plan_step_id)
                logger.action_failure(step.execution_id, code, message)
                if not recoverable:
                    engine_stopped = True
                continue

        # Enregistrement dans le dict de sortie (indépendamment de dry_run :
        # même en simulation, on veut voir ce qui AURAIT été soumis).
        if step.action in {"SELL", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "HIRE", "BUY_LAND"}:
            market_orders.append(list(outcome.action))
        elif step.worker_id is not None:
            worker_actions[step.worker_id] = list(outcome.action)

    return executed, failed, skipped, worker_actions, market_orders
