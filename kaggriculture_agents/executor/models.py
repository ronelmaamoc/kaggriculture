"""
Structures de données de l'ExecutorAgent.

Le point d'arrivée réel de ce module n'est pas un objet Python que l'on
interroge plus tard : c'est `ExecutionResult.turn_actions`, le dictionnaire
au format exact attendu en retour de `agent(obs)` (voir README.md du
module — Kaggriculture n'expose aucune API "un appel = une action avec
retour immédiat", uniquement ce dict soumis une fois par tour). Tout le
reste (`executed_steps`, `failed_steps`, `skipped_steps`...) sert à la
traçabilité et aux tests, pas à la communication avec le jeu lui-même.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class ExecutionStatus(Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ActionResult:
    """Retour d'un EnvironmentAdapter.execute_action(...) — voir environment_adapter.py."""
    success: bool
    turn: Optional[int] = None
    state: Optional[object] = None
    reward: Optional[float] = None
    message: Optional[str] = None
    error_code: Optional[str] = None


@dataclass(frozen=True)
class ExecutedStep:
    execution_id: str
    plan_step_id: str
    action: Tuple[str, ...]          # action Kaggriculture réellement envoyée, ex: ("HARVEST",) ou ("PLANT", "WHEAT")
    worker_id: Optional[str]
    success: bool
    turn: Optional[int]
    result: Optional[ActionResult] = None
    product: Optional[str] = None
    target: Optional[object] = None


@dataclass(frozen=True)
class ExecutionFailure:
    execution_id: str
    plan_step_id: str
    code: str                        # voir constants.py (ACTION_REJECTED, INVALID_TARGET, ...)
    message: str
    recoverable: bool


@dataclass(frozen=True)
class SkippedStep:
    execution_id: str
    plan_step_id: str
    reason: str                      # voir constants.py (DEPENDENCY_FAILED, FUTURE_TURN, ...)


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    executed_steps: Tuple[ExecutedStep, ...] = ()
    failed_steps: Tuple[ExecutionFailure, ...] = ()
    skipped_steps: Tuple[SkippedStep, ...] = ()
    actions_sent: int = 0
    actions_succeeded: int = 0
    actions_failed: int = 0
    turn_actions: Dict[str, list] = field(default_factory=lambda: {"farmer": ["PASS"], "hands": [], "market": []})
    explanation: str = ""
