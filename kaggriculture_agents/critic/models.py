"""
Structures de données produites par le CriticAgent.

Le CriticAgent NE modifie JAMAIS le `Plan` qu'il reçoit (spec section 36) :
il produit uniquement une `Critique`, un jugement séparé et immuable sur ce
plan. `CriticIssue` porte toute l'information nécessaire à l'explicabilité
(spec section 32) : quel problème (`code`), à quel point du plan
(`step_id`), sur quelle ressource, et la valeur attendue vs observée.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

# Importé uniquement pour exposer le plan corrigé au Coordinator.
from ..planner.models import Plan


class CritiqueStatus(Enum):
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    REJECTED = "rejected"


@dataclass(frozen=True)
class CriticIssue:
    code: str                       # ex: "BUDGET_EXCEEDED" (voir constants.py pour la liste complète)
    severity: str                   # "INFO" | "WARNING" | "ERROR" | "CRITICAL" (voir constants.py)
    message: str                    # explication lisible, autoportante (spec section 32)
    step_id: Optional[str] = None   # PlanStep.step_id concerné, None si le problème est global au plan
    resource: Optional[str] = None  # nom de la ressource concernée (ex: "SEED_WHEAT", "money"), si pertinent
    expected: Optional[object] = None  # valeur attendue / limite (ex: budget disponible)
    actual: Optional[object] = None    # valeur observée / demandée (ex: coût réel du plan)


@dataclass(frozen=True)
class Critique:
    status: CritiqueStatus
    issues: Tuple[CriticIssue, ...] = ()      # sévérité ERROR ou CRITICAL (bloquent APPROVED, spec section 31)
    warnings: Tuple[CriticIssue, ...] = ()    # sévérité INFO ou WARNING (n'empêchent jamais APPROVED)
    score: float = 1.0                        # qualité globale du plan, 0..1 (voir scoring.py) — INDÉPENDANT du statut
    confidence: float = 1.0                   # confiance de la critique elle-même, 0..1 (voir scoring.py)
    explanation: str = "Aucune proposition économique reçue."
    # Le Critic peut proposer une version corrigée du plan au lieu de simplement
    # le bloquer.
    revised_plan: Optional[Plan] = None
    recommendations: Tuple[str, ...] = ()
    stress_results: Tuple[object, ...] = ()
    robust_score: float = 1.0