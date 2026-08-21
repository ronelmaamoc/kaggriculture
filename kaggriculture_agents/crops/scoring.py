"""
scoring.py — Calcul des scores normalisés des propositions du CropAgent.

Formule commune (documentée, volontairement simple) :

    score = W_URGENCY  * urgency
          + W_VALUE     * value_norm
          + W_RISK      * risk
          - W_COST       * cost_norm
          - W_DISTANCE   * distance_norm

Tous les termes sont bornés dans [0, 1] avant pondération, et le score final
est reclippé dans [0, 1]. Les poids sont dans constants.py, modifiables
indépendamment de la logique de calcul (utile pour comparer des stratégies
dans le cadre du mémoire).
"""

from typing import Optional

from .constants import (
    COST_NORMALIZATION_CAP,
    DISTANCE_NORMALIZATION_CAP,
    FERTILIZER_BASE_PRICE,
    FERTILIZE_BONUS_DAYS,
    FERTILIZE_ONE_TIME_EXTRA_UNITS_PER_DAY,
    FERTILIZE_ONGOING_EXTRA_UNITS,
    VALUE_NORMALIZATION_CAP,
    W_COST,
    W_DISTANCE,
    W_RISK,
    W_URGENCY,
    W_VALUE,
)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _normalize(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return _clip01(value / cap)


def combine_score(
    urgency: float,
    expected_value: float,
    risk: float,
    cost: float,
    distance: Optional[float],
) -> float:
    value_norm = _normalize(expected_value, VALUE_NORMALIZATION_CAP)
    cost_norm = _normalize(cost, COST_NORMALIZATION_CAP)
    # distance=None signifie "aucun travailleur connu", pas "distance nulle" :
    # `distance or 0.0` transformerait silencieusement une absence
    # d'information en un bonus de proximité artificiel (distance zéro =
    # meilleur score possible). On traite l'inconnue comme une absence de
    # pénalité de distance, jamais comme une proximité gagnée.
    distance_norm = _normalize(distance, DISTANCE_NORMALIZATION_CAP) if distance is not None else 0.0

    raw = (
        W_URGENCY * _clip01(urgency)
        + W_VALUE * value_norm
        + W_RISK * _clip01(risk)
        - W_COST * cost_norm
        - W_DISTANCE * distance_norm
    )
    return _clip01(raw)


def score_harvest(urgency: float, expected_value: float, distance: Optional[float]) -> float:
    """Récolte : pas de risque (déjà acquis), pas de coût direct."""
    return combine_score(urgency=urgency, expected_value=expected_value, risk=0.0, cost=0.0, distance=distance)


def score_water(urgency: float, expected_value: float, risk: float, distance: Optional[float]) -> float:
    """Arrosage : la valeur en jeu est ce qu'on perdrait si la culture devenait une weed."""
    return combine_score(urgency=urgency, expected_value=expected_value, risk=risk, cost=0.0, distance=distance)


def score_plant(urgency: float, expected_value: float, seed_cost: float, distance: Optional[float]) -> float:
    """Plantation : pas de risque, mais un coût réel (la graine)."""
    return combine_score(urgency=urgency, expected_value=expected_value, risk=0.0, cost=seed_cost, distance=distance)


def score_fertilize(urgency: float, expected_value: float, distance: Optional[float]) -> float:
    """Fertilisation : coût fixe = prix de base du fertilisant."""
    return combine_score(
        urgency=urgency, expected_value=expected_value, risk=0.0,
        cost=FERTILIZER_BASE_PRICE, distance=distance,
    )


def estimate_fertilize_value(crop, crop_info: dict, price: float) -> float:
    """
    Heuristique de la valeur ajoutée par une FERTILIZE (voir constants.py pour
    la justification des règles utilisées, tirées de README.md).
    Ce n'est PAS une simulation exacte du moteur de jeu : juste une estimation
    locale suffisante pour comparer les propositions entre elles.
    """
    if crop_info["is_ongoing"]:
        return FERTILIZE_ONGOING_EXTRA_UNITS * price
    extra_units = FERTILIZE_ONE_TIME_EXTRA_UNITS_PER_DAY * FERTILIZE_BONUS_DAYS
    return extra_units * price
