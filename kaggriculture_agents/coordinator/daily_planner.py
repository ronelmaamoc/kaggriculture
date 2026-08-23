"""Daily operational planner — Routage fluide et priorisé (v7.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

Position = Tuple[int, int]
MARKET_ACTIONS = {
    "SELL",
    "BUY_SEED",
    "BUY_PRODUCT",
    "BUY_ANIMAL",
    "HIRE",
    "BUY_LAND",
}
MAINTENANCE_ACTIONS = {
    "WATER",
    "FEED",
    "CARE",
    "FERTILIZE",
    "COLLECT_FERTILIZER",
    "DUG",
    "PLANT",
    "BUILD_COOP",
    "BUILD_PASTURE",
    "PLACE",
    "PICKUP",
    "DIG",
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


def build_daily_plan(
    state,
    plan,
    max_fixed_tasks_per_worker: int = 6,
    start_hour: Optional[int] = None,
) -> DailyPlan:
    workers = list(getattr(state.workers, "all_workers", []) or [])
    if not workers:
        return DailyPlan(
            state.time.day,
            state.time.step,
            (),
            0,
            0,
            (),
            0,
            0,
            0,
            max(18, state.time.turns_per_day - 6),
            "Aucun worker disponible.",
        )

    candidates = [
        s
        for s in getattr(plan, "steps", ())
        if getattr(s, "worker_required", False)
        and getattr(s, "target", None) is not None
        and getattr(s, "action", "") not in MARKET_ACTIONS
        and getattr(s, "action", "") not in {"HOLD"}
    ]

    action_rank = {
        "FEED": 0,
        "WATER": 0,
        "HARVEST": 1,
        "CARE": 2,
        "DUG": 2,
        "DIG": 2,
        "FERTILIZE": 3,
        "PLANT": 4,
        "COLLECT_FERTILIZER": 4,
        "BUILD_COOP": 5,
        "BUILD_PASTURE": 5,
        "PICKUP": 5,
        "PLACE": 5,
    }

    candidates = sorted(
        candidates,
        key=lambda s: (
            action_rank.get(str(getattr(s, "action", "")), 9),
            -float(getattr(s, "priority", 0.0)),
            str(getattr(s, "target", "")),
            s.step_id,
        ),
    )
    candidates = candidates[: max(1, len(workers) * max_fixed_tasks_per_worker)]

    routes: Dict[str, List] = {w.worker_id: [] for w in workers}
    positions: Dict[str, Optional[Position]] = {
        w.worker_id: w.position for w in workers
    }
    by_id = {s.step_id: s for s in candidates}
    assigned: Dict[str, str] = {}

    for s in sorted(
        candidates,
        key=lambda x: (x.phase, -float(getattr(x, "priority", 0.0)), x.step_id),
    ):
        deps = [d for d in getattr(s, "depends_on", ()) if d in by_id]
        dependent_workers = [assigned[d] for d in deps if d in assigned]

        if dependent_workers:
            worker_id = dependent_workers[0]
            worker = next(w for w in workers if w.worker_id == worker_id)
        else:
            available = [
                w
                for w in workers
                if len(routes[w.worker_id]) < max_fixed_tasks_per_worker
            ]
            if not available:
                continue
            worker = min(
                available,
                key=lambda w: (
                    _dist(positions[w.worker_id], s.target),
                    len(routes[w.worker_id]),
                    w.worker_id,
                ),
            )

        routes[worker.worker_id].append(s)
        positions[worker.worker_id] = s.target
        assigned[s.step_id] = worker.worker_id

    turns = int(state.time.turns_per_day)
    current_hour = int(state.time.hour if start_hour is None else start_hour)
    market_start = min(max(18, turns - 6), max(0, turns - 1))

    tasks: List[DailyTask] = []
    for worker in workers:
        current = worker.position
        hour = current_hour
        route = routes[worker.worker_id]

        for source_step in route:
            target = source_step.target
            while current != target and hour < turns:
                dx = target[0] - current[0]
                dy = target[1] - current[1]
                if dx != 0:
                    action = "EAST" if dx > 0 else "WEST"
                    current = (current[0] + (1 if dx > 0 else -1), current[1])
                else:
                    action = "SOUTH" if dy > 0 else "NORTH"
                    current = (current[0], current[1] + (1 if dy > 0 else -1))

                tasks.append(
                    DailyTask(
                        task_id=f"move:{state.time.day}:{worker.worker_id}:{len(tasks)}",
                        action=action,
                        target=current,
                        product=None,
                        worker_id=worker.worker_id,
                        priority=0.0,
                        source_agent="daily",
                        reason="Déplacement",
                        planned_hour=hour,
                    )
                )
                hour += 1

            if hour >= turns:
                break

            tasks.append(
                DailyTask(
                    task_id=f"task:{source_step.step_id}:{worker.worker_id}",
                    action=source_step.action,
                    target=source_step.target,
                    product=source_step.product,
                    worker_id=worker.worker_id,
                    priority=float(getattr(source_step, "priority", 0.0)),
                    source_agent=str(
                        getattr(source_step, "source_agent", "daily")
                    ),
                    reason=str(getattr(source_step, "reason", "")),
                    planned_hour=hour,
                )
            )
            hour += 1

    maintenance_count = sum(1 for t in tasks if t.action in MAINTENANCE_ACTIONS)
    harvest_count = sum(1 for t in tasks if t.action in HARVEST_ACTIONS)
    movement_count = sum(
        1 for t in tasks if t.action in {"NORTH", "SOUTH", "EAST", "WEST"}
    )

    return DailyPlan(
        day=int(state.time.day),
        created_turn=int(state.time.step),
        workers=tuple(w.worker_id for w in workers),
        desired_workers=len(workers),
        recommended_hires=0,
        tasks=tuple(
            sorted(
                tasks,
                key=lambda t: (t.planned_hour, t.worker_id, t.task_id),
            )
        ),
        maintenance_count=maintenance_count,
        harvest_count=harvest_count,
        movement_count=movement_count,
        market_window_start=market_start,
        explanation=f"Jour {state.time.day}: {len(tasks)} tâches planifiées.",
    )