"""
validators.py — Vérifications finales avant production de l'ExecutionSchedule.

Deux responsabilités volontairement séparées (spec section 5 et 7) :

    1. check_critique_approved : le Coordinator ne doit JAMAIS tenter de
       coordonner un plan non approuvé -- il ne le "répare" pas, il refuse
       (spec section 5, 23).
    2. determine_status : une fois le schedule construit, détermine si le
       résultat est READY / PARTIAL / BLOCKED (spec section 7).
"""

from typing import Optional

from .constants import APPROVED_STATUS_VALUE, REASON_PLAN_NOT_APPROVED
from .models import ScheduleStatus


def check_critique_approved(critique) -> Optional[str]:
    """
    Retourne `None` si la critique autorise la coordination, sinon une
    explication lisible (utilisée telle quelle dans
    ExecutionSchedule.explanation).
    """
    if critique is None:
        return f"{REASON_PLAN_NOT_APPROVED} : aucune critique fournie"

    status_value = getattr(critique.status, "value", critique.status)
    if status_value != APPROVED_STATUS_VALUE:
        return f"{REASON_PLAN_NOT_APPROVED} : statut de la critique = {status_value!r} (APPROVED requis)"
    return None


def determine_status(total_plan_steps: int, blocked_count: int) -> ScheduleStatus:
    """
    - total_plan_steps == 0 : rien à coordonner -> READY (ce n'est pas un
      blocage, c'est un plan vide -- cohérent avec la convention
      "plan vide -> APPROVED" du CriticAgent).
    - blocked_count == 0 : tout le plan a pu être programmé -> READY.
    - 0 < blocked_count < total_plan_steps : une partie seulement -> PARTIAL.
    - blocked_count >= total_plan_steps : rien n'a pu être programmé -> BLOCKED.
    """
    if total_plan_steps == 0:
        return ScheduleStatus.READY
    if blocked_count == 0:
        return ScheduleStatus.READY
    if blocked_count < total_plan_steps:
        return ScheduleStatus.PARTIAL
    return ScheduleStatus.BLOCKED
