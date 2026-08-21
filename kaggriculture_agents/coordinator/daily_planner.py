"""Daily operational planner for V5.8.3.

Worker work is replanned from the current observation.  This is intentional:
a PLANT/HARVEST/DIG/PLACE action changes the FarmState immediately, so a
plan frozen for the whole day can target stale entities.  The planner only
commits the immediately actionable phase (phase 0) and recomputes routes from
the workers' actual positions on every turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import ExecutionSchedule, ExecutionStep, ScheduleStatus

Position = Tuple[int, int]
MARKET_ACTIONS = {"SELL", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "HIRE", "BUY_LAND"}
MAINTENANCE_ACTIONS = {
    "WATER", "FEED", "CARE", "FERTILIZE", "COLLECT_FERTILIZER", "DUG",
    "PLANT", "BUILD_COOP", "BUILD_PASTURE", "PLACE", "PICKUP", "DIG",
}
HARVEST_ACTIONS = {"HARVEST"}

@dataclass(frozen=True)
class DailyTask:
    task_id: str
    action: str
    target: Optional[Position]
    product: Optional[str]
    worker_id: str
    priority: float
    source_agent: str
    reason: str
    planned_hour: int
    fixed: bool = True

@dataclass(frozen=True)
class DailyPlan:
    day: int
    created_turn: int
    workers: Tuple[str, ...]
    desired_workers: int
    recommended_hires: int
    tasks: Tuple[DailyTask, ...]
    maintenance_count: int
    harvest_count: int
    movement_count: int
    market_window_start: int
    explanation: str


def _dist(a: Optional[Position], b: Optional[Position]) -> int:
    if a is None or b is None:
        return 9999
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _worker_count_needed(tasks: Sequence, turns_per_day: int, workers: Sequence = ()) -> int:
    # One worker consumes one slot for both movement and work.  Estimate the
    # daily workload as task slots + the nearest-worker travel needed to reach
    # each target.  Kaggriculture's practical worker ceiling in this strategy
    # is the farmer plus four hands, so never recommend more than five.
    turns = max(1, int(turns_per_day))
    worker_positions = [getattr(w, "position", None) for w in workers]
    workload = 0
    for task in tasks:
        target = getattr(task, "target", None)
        nearest = min((_dist(pos, target) for pos in worker_positions), default=0)
        workload += 1 + min(nearest, turns)
    return max(1, min(5, (workload + turns - 1) // turns))


def _category(action: str) -> int:
    if action in HARVEST_ACTIONS:
        return 2
    if action in MAINTENANCE_ACTIONS:
        return 1
    return 3


def build_daily_plan(state, plan, max_fixed_tasks_per_worker: int = 6, start_hour: Optional[int] = None) -> DailyPlan:
    """Build a worker-specific route/task list from an approved plan.

    The planner deliberately ignores market steps here.  Market decisions are
    recalculated from the end-of-day state, while worker work is fixed for the
    current day.
    """
    workers = list(getattr(state.workers, "all_workers", []) or [])
    if not workers:
        return DailyPlan(state.time.day, state.time.step, (), 0, 0, (), 0, 0, 0, max(18, state.time.turns_per_day - 6), "Aucun worker disponible.")

    # Keep the approved operational portfolio, but recompute it every turn.
    # Dependencies remain ordered by phase; the resulting route is only a
    # proposal for the remaining hours and is discarded at the next obs.
    candidates = [
        s for s in getattr(plan, "steps", ())
        if getattr(s, "worker_required", False)
        and getattr(s, "target", None) is not None
        and getattr(s, "action", "") not in MARKET_ACTIONS
        and getattr(s, "action", "") not in {"HOLD"}
    ]
    # Urgent survival/maintenance tasks must beat investment/optimization.
    # The economic Planner already scored the proposals; this is the final
    # operational safety gate.
    action_rank = {
        "FEED": 0, "WATER": 0, "HARVEST": 1, "CARE": 2,
        "DUG": 2, "DIG": 2, "FERTILIZE": 3, "PLANT": 4,
        "COLLECT_FERTILIZER": 4, "BUILD_COOP": 5, "BUILD_PASTURE": 5,
        "PICKUP": 5, "PLACE": 5,
    }
    candidates = sorted(
        candidates,
        key=lambda s: (action_rank.get(str(getattr(s, "action", "")), 9),
                       -float(getattr(s, "priority", 0.0)),
                       -float(getattr(s, "confidence", 1.0)),
                       str(getattr(s, "target", "")), s.step_id),
    )
    candidates = candidates[: max(1, len(workers) * max_fixed_tasks_per_worker)]

    desired = _worker_count_needed(candidates, int(state.time.turns_per_day), workers)
    recommended_hires = max(0, desired - len(workers))

    routes: Dict[str, List] = {w.worker_id: [] for w in workers}
    positions: Dict[str, Optional[Position]] = {w.worker_id: w.position for w in workers}

    # Assign by category while preserving locality.  Dependencies between
    # worker tasks are kept on the same worker whenever possible (important
    # for BUILD/PICKUP/PLACE animal lifecycle chains).
    by_id = {s.step_id: s for s in candidates}
    assigned: Dict[str, str] = {}
    unassigned = list(candidates)

    for s in sorted(candidates, key=lambda x: (x.phase, -float(getattr(x, "priority", 0.0)), x.step_id)):
        deps = [d for d in getattr(s, "depends_on", ()) if d in by_id]
        dependent_workers = [assigned[d] for d in deps if d in assigned]
        if dependent_workers:
            worker_id = dependent_workers[0]
            worker = next(w for w in workers if w.worker_id == worker_id)
        else:
            available = [w for w in workers if len(routes[w.worker_id]) < max_fixed_tasks_per_worker]
            if not available:
                continue
            worker = min(
                available,
                key=lambda w: (
                    _dist(positions[w.worker_id], s.target),
                    len(routes[w.worker_id]),
                    -float(getattr(s, "priority", 0.0)),
                    w.worker_id,
                ),
            )
        routes[worker.worker_id].append(s)
        positions[worker.worker_id] = s.target
        assigned[s.step_id] = worker.worker_id
        if s in unassigned:
            unassigned.remove(s)

    # Route order is deliberately phase-like: morning movement is generated
    # from the route, maintenance/plantation before harvest, while dependency
    # order remains stable inside a category.
    for worker in workers:
        routes[worker.worker_id].sort(
            key=lambda s: (int(getattr(s, "phase", 0)), _category(s.action),
                           -float(getattr(s, "priority", 0.0)), s.step_id)
        )

    turns = int(state.time.turns_per_day)
    current_hour = int(state.time.hour if start_hour is None else start_hour)
    current_hour = max(0, min(current_hour, max(0, turns - 1)))
    market_start = min(max(18, turns - 6), max(0, turns - 1))

    tasks: List[DailyTask] = []
    for worker in workers:
        current = worker.position
        hour = current_hour
        # Morning movement is explicit.  It consumes the same worker slot as
        # every other action, so the subsequent task starts only after arrival.
        route = routes[worker.worker_id]
        for source_step in route:
            target = source_step.target
            while current != target and hour < turns:
                dx = target[0] - current[0]
                dy = target[1] - current[1]
                if dx:
                    action = "EAST" if dx > 0 else "WEST"
                    current = (current[0] + (1 if dx > 0 else -1), current[1])
                else:
                    action = "SOUTH" if dy > 0 else "NORTH"
                    current = (current[0], current[1] + (1 if dy > 0 else -1))
                tasks.append(DailyTask(
                    task_id=f"move:{state.time.day}:{worker.worker_id}:{len(tasks)}",
                    action=action, target=current, product=None, worker_id=worker.worker_id,
                    priority=0.0, source_agent="daily", reason="Déplacement planifié vers la prochaine tâche", planned_hour=hour,
                ))
                hour += 1
            if hour >= turns:
                break
            # No artificial morning/afternoon gates: WATER/FEED can be urgent
            # immediately after the previous observation, and HARVEST should
            # not be delayed merely because it is early in the day.
            if hour >= turns:
                break
            tasks.append(DailyTask(
                task_id=f"task:{source_step.step_id}:{worker.worker_id}",
                action=source_step.action, target=source_step.target, product=source_step.product,
                worker_id=worker.worker_id, priority=float(getattr(source_step, "priority", 0.0)),
                source_agent=str(getattr(source_step, "source_agent", "daily")), reason=str(getattr(source_step, "reason", "")),
                planned_hour=hour,
            ))
            hour += 1

    maintenance_count = sum(1 for t in tasks if t.action in MAINTENANCE_ACTIONS)
    harvest_count = sum(1 for t in tasks if t.action in HARVEST_ACTIONS)
    movement_count = sum(1 for t in tasks if t.action in {"NORTH", "SOUTH", "EAST", "WEST"})
    explanation = (
        f"Jour {state.time.day} h{current_hour}: {len(workers)} worker(s), "
        f"{len(tasks)} créneau(x) opérationnel(s); déplacement={movement_count}, "
        f"entretien/plantation={maintenance_count}, récolte={harvest_count}; "
        f"marché dynamique à partir de h{market_start}."
    )
    return DailyPlan(
        day=int(state.time.day), created_turn=int(state.time.step),
        workers=tuple(w.worker_id for w in workers), desired_workers=desired,
        recommended_hires=recommended_hires, tasks=tuple(sorted(tasks, key=lambda t: (t.planned_hour, t.worker_id, t.task_id))),
        maintenance_count=maintenance_count, harvest_count=harvest_count, movement_count=movement_count,
        market_window_start=market_start, explanation=explanation,
    )


def daily_actions_for_turn(daily_plan: DailyPlan, state) -> Dict[str, list]:
    """Return the fixed worker action for the current turn.

    Only one action per worker is emitted.  A task scheduled at the current
    hour is used; otherwise PASS.  Market orders are intentionally absent.
    """
    hour = int(state.time.hour)
    out = {w.worker_id: ["PASS"] for w in state.workers.all_workers}
    for task in daily_plan.tasks:
        if task.planned_hour == hour and task.worker_id in out:
            if task.action == "PLANT":
                out[task.worker_id] = ["PLANT", task.product]
            elif task.action == "PLACE":
                out[task.worker_id] = ["PLACE", task.product, max(1, int(round(1)))]
            elif task.action in {"EAST", "WEST", "NORTH", "SOUTH", "DIG", "WATER", "HARVEST", "FERTILIZE", "FEED", "CARE", "COLLECT_FERTILIZER", "BUILD_COOP", "BUILD_PASTURE", "PICKUP"}:
                out[task.worker_id] = [task.action]
    return out
