"""
scoring.py — Calcul des scores normalisés des propositions de l'AnimalAgent.

Formule commune (documentée, volontairement simple — identique à celle du
CropAgent pour que les scores des deux agents restent comparables) :

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


def score_feed(urgency: float, expected_value: float, risk: float, cost: float, distance: Optional[float]) -> float:
    """FEED : la valeur en jeu est ce qui serait perdu si l'animal s'échappait ; coût = 1 blé."""
    return combine_score(urgency=urgency, expected_value=expected_value, risk=risk, cost=cost, distance=distance)


def score_care(urgency: float, expected_value: float, distance: Optional[float]) -> float:
    """CARE : pas de risque de perte, pas de coût direct (juste un tour)."""
    return combine_score(urgency=urgency, expected_value=expected_value, risk=0.0, cost=0.0, distance=distance)


def score_harvest(urgency: float, expected_value: float, distance: Optional[float]) -> float:
    """HARVEST : production déjà acquise, pas de risque, pas de coût direct."""
    return combine_score(urgency=urgency, expected_value=expected_value, risk=0.0, cost=0.0, distance=distance)


def score_fertilizer(urgency: float, expected_value: float, distance: Optional[float]) -> float:
    """COLLECT_FERTILIZER : pas de risque, pas de coût direct."""
    return combine_score(urgency=urgency, expected_value=expected_value, risk=0.0, cost=0.0, distance=distance)


def score_expansion(urgency: float, expected_value: float, cost: float, distance: Optional[float]) -> float:
    """EXPANSION_OPPORTUNITY : coût = prix d'achat de l'animal (signal seulement, pas un achat)."""
    return combine_score(urgency=urgency, expected_value=expected_value, risk=0.0, cost=cost, distance=distance)


def estimate_feed_risk_value(animal, animal_info: dict, price: float) -> float:
    """
    Heuristique de la valeur en jeu si l'animal n'est PAS nourri à temps
    (donc s'échappe, cf. README.md) : le coût d'achat déjà englouti, plus la
    production déjà accumulée sur la case et qui serait perdue avec lui.
    Ce n'est PAS une simulation exacte du moteur de jeu : juste un ordre de
    grandeur pour comparer les propositions entre elles.
    """
    return animal_info["purchase_cost"] + animal.yield_units * price


def estimate_expansion_value(animal_type: str, animal_info: dict, price: float) -> float:
    """
    Heuristique de profit potentiel d'une expansion : capacité de stockage
    maximale de production (max_held) au prix courant, moins le coût
    d'achat. Même logique que CropAgent.find_plant_tasks pour PLANT.
    """
    return max(animal_info["max_held"] * price - animal_info["purchase_cost"], 0.0)