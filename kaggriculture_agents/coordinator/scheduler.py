"""
scheduler.py — Construction du schedule d'exécution à partir d'un Plan.

Algorithme (spec section 30), en confiance décroissante dans les steps :

    1. vérification défensive des dépendances (cycle, ordre de phase)
       -> steps invalides écartés, jamais "réparés" (spec section 23)
    2. regroupement des steps restants par phase
    3. affectation des workers, phase par phase (worker_allocator)
    4. steps non affectables -> écartés (defense in depth)
    5. vérification défensive des conflits de worker (conflict_resolver)
       -> steps en conflit -> écartés
    6. datation en tours de jeu (resource_scheduler)
    7. construction des ExecutionStep finaux, triés (phase, step_id)

Ne modifie jamais les `PlanStep` reçus (lecture seule, spec section 27).
"""

from typing import Dict, List, Sequence, Tuple

from . import conflict_resolver, dependency_graph, resource_scheduler, worker_allocator
from .models import BlockedStep, ExecutionStep


def schedule(
    steps_in: Sequence,
    workers: Sequence[Tuple[str, object]],
    base_turn: int,
) -> Tuple[List[ExecutionStep], List[BlockedStep]]:
    by_id = {step.step_id: step for step in steps_in}
    schedulable_ids = set(by_id.keys())
    blocked: List[BlockedStep] = []

    # --- 1. dépendances : cycles + ordre de phase (défensif) --------------
    graph = dependency_graph.build_graph(steps_in)
    for step_id in sorted(dependency_graph.detect_cycles(graph)):
        blocked.append(BlockedStep(
            plan_step_id=step_id, action=by_id[step_id].action,
            reason="cycle de dépendances détecté (incohérence amont, defense in depth)",
        ))
        schedulable_ids.discard(step_id)

    for step_id, dep_id, message in dependency_graph.find_invalid_phase_order(steps_in):
        if step_id in schedulable_ids:
            blocked.append(BlockedStep(
                plan_step_id=step_id, action=by_id[step_id].action,
                reason=f"ordre de dépendance invalide vis-à-vis de {dep_id} : {message}",
            ))
            schedulable_ids.discard(step_id)

    schedulable_steps = [s for s in steps_in if s.step_id in schedulable_ids]

    # --- 2-3. regroupement par phase + affectation des workers ------------
    # `step.worker_required` est la décision DÉJÀ prise par PlannerAgent
    # (kaggriculture_agents/planner/models.PlanStep.worker_required) : on s'appuie dessus
    # plutôt que de la redériver localement depuis `step.action`, pour ne
    # jamais risquer de diverger de la décision amont (voir README.md).
    worker_steps_by_phase: Dict[int, List] = {}
    for step in schedulable_steps:
        if step.worker_required:
            worker_steps_by_phase.setdefault(step.phase, []).append(step)

    assignment, unassigned = worker_allocator.allocate_workers(worker_steps_by_phase, workers)

    # --- 4. steps non affectables (defense in depth) -----------------------
    for step_id, reason in unassigned:
        blocked.append(BlockedStep(plan_step_id=step_id, action=by_id[step_id].action, reason=reason))
        schedulable_ids.discard(step_id)

    # --- 5. conflits de worker (defense in depth) ---------------------------
    conflicts = conflict_resolver.detect_worker_conflicts(schedulable_steps, assignment)
    for phase, worker_id, step_ids in conflicts:
        for step_id in step_ids:
            if step_id in schedulable_ids:
                blocked.append(BlockedStep(
                    plan_step_id=step_id, action=by_id[step_id].action,
                    reason=f"conflit : worker {worker_id} déjà affecté en phase {phase} (defense in depth)",
                ))
                schedulable_ids.discard(step_id)

    final_steps = sorted(
        (s for s in schedulable_steps if s.step_id in schedulable_ids),
        key=lambda s: (s.phase, s.step_id),
    )

    # --- 6-7. datation + construction finale --------------------------------
    execution_steps = [
        ExecutionStep(
            execution_id=f"exec:{index}",
            plan_step_id=step.step_id,
            action=step.action,
            source_agent=step.source_agent,
            target=step.target,
            product=step.product,
            phase=step.phase,
            estimated_turn=resource_scheduler.estimated_turn_for_phase(base_turn, step.phase),
            worker_id=assignment.get(step.step_id),
            dependencies=tuple(step.depends_on),
            quantity=getattr(step, "quantity", 1.0),
            reason=step.reason,
        )
        for index, step in enumerate(final_steps)
    ]

    return execution_steps, blocked
