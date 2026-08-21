"""
rules.py — Règles de candidature/qualification pour l'EconomyAgent.

Une fonction "rule" répond uniquement à la question "cette proposition
respecte-t-elle telle contrainte économique ?" (booléen ou catégorie). Elle
ne calcule pas de score — ça, c'est le rôle de scoring.py. Elle ne modifie
jamais FarmState ni les propositions reçues (spec sections 5 et 30 :
lecture seule, aucun appel direct aux autres agents).
"""

from typing import Optional

from .constants import SAFE_INVESTMENT_MAX_SHARE


def is_affordable(cost: float, safe_budget: float) -> bool:
    """Une dépense est finançable si elle tient dans le budget sécurisé."""
    return cost <= safe_budget


def is_profitable(profit: float) -> bool:
    """Rentable au sens strict : revenu attendu supérieur au coût."""
    return profit > 0


def is_safe_investment(cost: float, safe_budget: float, max_share: float = SAFE_INVESTMENT_MAX_SHARE) -> bool:
    """
    Un investissement est jugé "sûr" s'il n'engage pas plus d'une fraction
    du budget sécurisé (spec section 23 : investir 900 sur 1000 de
    trésorerie est risqué même si l'opération semble rentable).
    """
    if cost <= 0:
        return True
    if safe_budget <= 0:
        return False
    return cost <= safe_budget * max_share


def is_time_feasible(remaining_days: int, required_days: Optional[int]) -> bool:
    """
    Une action nécessitant un délai de production n'est faisable que si le
    temps restant le permet (spec section 34-35). `required_days = None`
    signifie une action immédiate (récolte, vente, soin...) : toujours
    faisable tant que la partie n'est pas terminée.
    """
    if required_days is None:
        return True
    return remaining_days >= required_days


def is_resource_efficient(resource_efficiency: float, threshold: float = 0.0) -> bool:
    """Une action est jugée efficace en ressources si son ratio dépasse un seuil minimal."""
    return resource_efficiency > threshold


def resource_level(quantity: float, critical_threshold: float, limited_threshold: float) -> str:
    """
    Catégorise le niveau d'une ressource (spec section 12-13) :
    CRITICAL (risque de bloquer une activité), LIMITED (à surveiller),
    ABUNDANT (pas de contrainte identifiée).
    """
    if quantity <= critical_threshold:
        return "CRITICAL"
    if quantity <= limited_threshold:
        return "LIMITED"
    return "ABUNDANT"