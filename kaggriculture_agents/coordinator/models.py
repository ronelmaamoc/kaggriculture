"""
Structures de données produites par le CoordinatorAgent.

ExecutionSchedule / ExecutionStep sont le résultat final de ce module :
une transformation d'un `Plan` déjà validé (`Critique.status == APPROVED`)
en une séquence d'exécution concrète -- ordonnée, affectée à des workers
réels, datée en tours de jeu. Ce n'est TOUJOURS PAS une action Kaggriculture
exécutable : ce sera le rôle du futur ExecutorAgent (hors scope ici).

BlockedStep suit exactement le même principe que
`kaggriculture_agents.planner.models.RejectedProposal` : tracer CE QUI a été exclu et
POURQUOI, plutôt que d'échouer silencieusement ou de "réparer" le plan
(spec section 23, "Ne pas réparer automatiquement").
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class ScheduleStatus(Enum):
    READY = "ready"      # toutes les actions du plan ont pu être programmées
    PARTIAL = "partial"  # une partie seulement (voir ExecutionSchedule.blocked)
    BLOCKED = "blocked"  # rien n'a pu être programmé (plan non approuvé, ou tout est bloqué)


@dataclass(frozen=True)
class ExecutionStep:
    execution_id: str               # identifiant d'exécution, ex: "exec:0" (ordre final, distinct de plan_step_id)
    plan_step_id: str                # PlanStep.step_id d'origine (traçabilité)
    action: str                     # reprise de PlanStep.action
    source_agent: str                # reprise de PlanStep.source_agent
    target: Optional[object]        # reprise de PlanStep.target
    product: Optional[str]          # reprise de PlanStep.product
    phase: int                      # reprise de PlanStep.phase (jamais recalculée, voir README)
    estimated_turn: int              # tour de jeu estimé (state.time.step + phase * TURNS_PER_PHASE)
    worker_id: Optional[str]         # "farmer" / "hand_0"... ; None si l'action n'en nécessite pas (ex: SELL)
    dependencies: Tuple[str, ...] = ()  # plan_step_id des steps dont celui-ci dépend
    quantity: float = 1.0              # quantité pour les ordres marché
    reason: str = ""                 # reprise de PlanStep.reason (audit / debug)


@dataclass(frozen=True)
class BlockedStep:
    plan_step_id: str
    action: str
    reason: str                     # explication lisible, jamais une simple constante (spec section 22-24)


@dataclass(frozen=True)
class ExecutionSchedule:
    steps: Tuple[ExecutionStep, ...] = field(default_factory=tuple)
    total_steps: int = 0
    estimated_turns: int = 0        # nombre de tours de jeu couverts par le schedule (0 si vide)
    status: ScheduleStatus = ScheduleStatus.BLOCKED
    explanation: str = ""
    blocked: Tuple[BlockedStep, ...] = field(default_factory=tuple)
