"""
scoring.py — Calcul du score diagnostique et de la confiance de la
Critique (spec section 30 et 32).

Ces deux grandeurs sont volontairement INDÉPENDANTES du statut
(rules.determine_status) : le statut se décide uniquement à partir des
sévérités présentes ; le score et la confiance ne servent qu'à qualifier
"à quel point" le plan est propre, pour l'explicabilité et un futur usage
comparatif (ex: choisir entre deux plans NEEDS_REVISION).
"""

from typing import Sequence

from .constants import CONFIDENCE_PENALTY_CAP, SEVERITY_CONFIDENCE_PENALTY, SEVERITY_SCORE_PENALTY
from .models import CriticIssue


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def calculate_critique_score(issues: Sequence[CriticIssue]) -> float:
    """
    score = 1.0 - somme des pénalités par sévérité (spec section 30),
    plafonné à [0, 1]. Purement diagnostique : n'intervient jamais dans le
    statut (voir rules.py).
    """
    total_penalty = sum(SEVERITY_SCORE_PENALTY.get(issue.severity, 0.0) for issue in issues)
    return _clip01(1.0 - total_penalty)


def calculate_confidence(issues: Sequence[CriticIssue]) -> float:
    """
    confidence = 1.0 - somme des pénalités de confiance, plafonnée à
    CONFIDENCE_PENALTY_CAP avant soustraction (de nombreux petits
    problèmes n'effondrent pas la confiance de la critique elle-même,
    seulement sa "propreté" mesurée par le score).
    """
    total_penalty = sum(SEVERITY_CONFIDENCE_PENALTY.get(issue.severity, 0.0) for issue in issues)
    total_penalty = min(total_penalty, CONFIDENCE_PENALTY_CAP)
    return _clip01(1.0 - total_penalty)