"""
scoring.py — Calcul des grandeurs économiques et du score final de
l'EconomyAgent.

Toutes les fonctions sont pures (aucun accès à FarmState) : elles reçoivent
des nombres déjà extraits par analyzers.py. Chaque terme du score est borné
dans [0, 1] avant pondération, et le score final est reclippé dans [0, 1],
comme dans CropAgent/AnimalAgent/MarketAgent. Les poids et bornes sont dans
constants.py.
"""

from typing import Optional

from .constants import (
    CASH_DELTA_CAP,
    PROFIT_NORMALIZATION_CAP,
    RESOURCE_EFFICIENCY_NORMALIZATION_CAP,
    ROI_NORMALIZATION_CAP,
    W_LIQUIDITY,
    W_PROFIT,
    W_RESOURCE,
    W_RISK,
    W_ROI,
    W_URGENCY,
)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _normalize(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return _clip01(value / cap)


def calculate_profitability(expected_revenue: float, cost: float) -> float:
    """
    profit = expected_revenue - cost (spec section 16).
    `cost` n'est jamais None ici : soit une dépense réelle documentée
    (graine, achat d'animal), soit 0 quand l'action n'engage aucune
    dépense directe connue (récolte, soin, vente...) — ce n'est pas une
    valeur inventée, c'est la valeur exacte pour ces actions.
    """
    return expected_revenue - cost


def calculate_roi(profit: float, cost: float) -> Optional[float]:
    """ROI = profit / cost. None si cost <= 0 (spec section 17 : jamais de division par zéro)."""
    if cost <= 0:
        return None
    return profit / cost


def calculate_cash_delta(expected_revenue: float, cost: float) -> float:
    """
    Impact net sur la trésorerie (spec section 19). Dans cette version,
    équivalent à `calculate_profitability` : aucun flux non monétaire
    différé n'est modélisé séparément (limite documentée dans le README).
    """
    return expected_revenue - cost


def calculate_liquidity_score(cash_delta: float, cap: float = CASH_DELTA_CAP) -> float:
    """
    Traduit cash_delta (peut être négatif) en un score [0, 1] : 0.5 = neutre,
    1.0 = fort apport de trésorerie, 0.0 = forte sortie de trésorerie.
    """
    return _clip01((cash_delta + cap) / (2 * cap))


def calculate_risk(cost: float, safe_budget: float) -> float:
    """
    Risque financier = proportion du budget sécurisé engagée par cette
    proposition (spec section 23). Aucun coût -> aucun risque financier
    direct. Coût positif sans budget sécurisé disponible -> risque maximal.
    """
    if cost <= 0:
        return 0.0
    if safe_budget <= 0:
        return 1.0
    return _clip01(cost / safe_budget)


def calculate_resource_efficiency(profit: float, cost: float, quantity: float = 1.0) -> float:
    """
    Rendement par unité de ressource engagée (spec section 36). Utilise le
    coût monétaire quand il existe (ressource rare = l'argent immobilisé) ;
    sinon retombe sur une quantité de produit connue (ex: revenu par unité
    vendue) ; sinon 0.0 (aucune base fiable disponible).
    """
    if cost > 0:
        return profit / cost
    if quantity and quantity > 0:
        return profit / quantity
    return 0.0


def calculate_economic_score(
    profit: float,
    roi: Optional[float],
    cash_delta: float,
    risk: float,
    urgency: float,
    resource_efficiency: float,
    time_feasible: bool,
) -> float:
    """
    economic_score = W_PROFIT*profit_norm + W_ROI*roi_norm + W_LIQUIDITY*liquidity_score
                    + W_URGENCY*urgency + W_RESOURCE*resource_norm - W_RISK*risk

    Forcé à 0.0 si l'action n'est pas jouable dans le temps restant
    (spec section 35 : "if production_time > remaining_time: feasibility = 0").
    """
    if not time_feasible:
        return 0.0

    profit_norm = _normalize(profit, PROFIT_NORMALIZATION_CAP)
    roi_norm = _normalize(roi if roi is not None else 0.0, ROI_NORMALIZATION_CAP)
    liquidity_score = calculate_liquidity_score(cash_delta)
    resource_norm = _normalize(resource_efficiency, RESOURCE_EFFICIENCY_NORMALIZATION_CAP)

    raw = (
        W_PROFIT * profit_norm
        + W_ROI * roi_norm
        + W_LIQUIDITY * liquidity_score
        + W_URGENCY * _clip01(urgency)
        + W_RESOURCE * resource_norm
        - W_RISK * _clip01(risk)
    )
    return _clip01(raw)