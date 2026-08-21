"""Per-turn forensic trace for Kaggriculture multi-agent debugging."""
from __future__ import annotations
from dataclasses import asdict, is_dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any


def jsonable(obj: Any):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return {k: jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return {k: jsonable(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return repr(obj)


class DecisionTrace:
    """Append-only JSONL trace: one complete pipeline snapshot per turn."""
    def __init__(self, path: str | Path | None = None, enabled: bool = False):
        self.enabled = bool(enabled or path)
        self.path = Path(path) if path else Path("logs/kaggriculture_trace.jsonl")
        self._episode = 0
        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def reset_episode(self):
        self._episode += 1

    def write(self, *, turn: int, state, crop, animal, market, investment, economy,
              plan, critique, schedule, execution, final_actions, calendar=None,
              daily_plan=None, error=None):
        if not self.enabled:
            return
        record = {
            "episode": self._episode,
            "turn": turn,
            "state": jsonable(state),
            "agents": {
                "crop": jsonable(crop),
                "animal": jsonable(animal),
                "market": jsonable(market),
                "investment": jsonable(investment),
                "economy": jsonable(economy),
                "planner": jsonable(plan),
                "critic": jsonable(critique),
                "coordinator": jsonable(schedule),
                "executor": jsonable(execution),
            },
            "calendar": jsonable(calendar),
            "daily_plan": jsonable(daily_plan),
            "final_actions": jsonable(final_actions),
            "error": error,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
