"""
rules.py — Règles de décision du CriticAgent (spec sections 29-31).

Fonctions pures, sans accès à `state`/`plan` : elles ne raisonnent que sur
la liste de `CriticIssue` déjà collectée par validators.py / analyzers.py /
conflicts.py. Le statut ne dépend QUE des sévérités présentes (spec section
30 : "les violations critiques doivent avoir priorité sur le score
numérique") — jamais du score, qui reste un indicateur diagnostique séparé
(voir scoring.py).
"""

from typing import Sequence

from .constants import SEVERITY_CRITICAL, SEVERITY_ERROR
from .models import CriticIssue, CritiqueStatus


def is_critical(issue: CriticIssue) -> bool:
    return issue.severity == SEVERITY_CRITICAL


def is_error(issue: CriticIssue) -> bool:
    return issue.severity == SEVERITY_ERROR


def is_warning(issue: CriticIssue) -> bool:
    return issue.severity not in (SEVERITY_ERROR, SEVERITY_CRITICAL)


def should_reject(issues: Sequence[CriticIssue]) -> bool:
    """Au moins une violation CRITICAL : aucun réordonnancement ne répare le plan (spec section 31)."""
    return any(is_critical(i) for i in issues)


def should_approve(issues: Sequence[CriticIssue]) -> bool:
    """Aucune violation bloquante (ERROR ou CRITICAL) : seulement des WARNING/INFO, ou rien du tout."""
    return not should_reject(issues) and not any(is_error(i) for i in issues)


def determine_status(issues: Sequence[CriticIssue]) -> CritiqueStatus:
    """
    Règle de décision (spec section 31) :

        CRITICAL présent   -> REJECTED       (violation non corrigeable par réordonnancement)
        ERROR présent       -> NEEDS_REVISION (corrigeable, mais bloque APPROVED)
        sinon (WARNING/INFO seulement, ou rien) -> APPROVED
    """
    if should_reject(issues):
        return CritiqueStatus.REJECTED
    if any(is_error(i) for i in issues):
        return CritiqueStatus.NEEDS_REVISION
    return CritiqueStatus.APPROVED