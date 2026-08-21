"""
scoring.py — Calcul des scores normalisés des propositions du MarketAgent.

Trois formules distinctes (une par action), toutes construites sur le même
principe que CropAgent/AnimalAgent : chaque terme est borné dans [0, 1]
avant pondération, et le score final est reclippé dans [0, 1]. Les poids
sont dans constants.py, modifiables indépendamment de la logique de calcul.
"""

from typing import Optional

from .constants import (
    INVENTORY_NORMALIZATION_CAP,
    PRICE_POSITION_NORMALIZATION_CAP,
    VALUE_NORMALIZATION_CAP,
    W_INVENTORY_HOLD,
    W_INVENTORY_SELL,
    W_PRICE_HOLD,
    W_PRICE_PRODUCE,
    W_PRICE_SELL,
    W_TIME_PRODUCE,
    W_VALUE_PRODUCE,
    W_VALUE_SELL,
)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _normalize(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return _clip01(value / cap)


def price_position(normalized_price: float) -> float:
    """
    Traduit normalized_price (référence = 1.0 au prix de base) en un score
    [0, 1] où 1.0 = très favorable à la vente / à la production, 0.0 = très
    défavorable. Utilise PRICE_POSITION_NORMALIZATION_CAP comme borne haute
    documentée (voir constants.py).
    """
    return _normalize(normalized_price, PRICE_POSITION_NORMALIZATION_CAP)


def score_sell(normalized_price: float, expected_value: float, available_quantity: float) -> float:
    price_score = price_position(normalized_price)
    value_norm = _normalize(expected_value, VALUE_NORMALIZATION_CAP)
    inventory_norm = _normalize(available_quantity, INVENTORY_NORMALIZATION_CAP)

    raw = (
        W_PRICE_SELL * price_score
        + W_VALUE_SELL * value_norm
        + W_INVENTORY_SELL * inventory_norm
    )
    return _clip01(raw)


def score_hold(normalized_price: float, available_quantity: float) -> float:
    """
    HOLD est d'autant plus pertinent que le prix est bas (donc on pondère
    l'inverse de price_position) et qu'on a du stock à conserver.
    """
    price_score = price_position(normalized_price)
    inventory_norm = _normalize(available_quantity, INVENTORY_NORMALIZATION_CAP)

    raw = W_PRICE_HOLD * (1.0 - price_score) + W_INVENTORY_HOLD * inventory_norm
    return _clip01(raw)


def score_produce(normalized_price: float, expected_value: float, time_margin_ratio: float) -> float:
    price_score = price_position(normalized_price)
    value_norm = _normalize(expected_value, VALUE_NORMALIZATION_CAP)
    time_score = _clip01(time_margin_ratio)

    raw = (
        W_PRICE_PRODUCE * price_score
        + W_VALUE_PRODUCE * value_norm
        + W_TIME_PRODUCE * time_score
    )
    return _clip01(raw)


def time_margin_ratio(remaining_days: int, first_yield_day: int) -> float:
    """
    Ratio [0, 1] représentant la marge de temps disponible au-delà du
    minimum requis pour obtenir un premier rendement. 0.0 = juste assez de
    temps, 1.0 (ou plus, reclippé) = large marge.
    """
    if first_yield_day <= 0:
        return 1.0
    margin = remaining_days - first_yield_day
    return _clip01(margin / first_yield_day)


def estimate_sell_value(quantity: float, current_price: float) -> float:
    """
    Valeur brute d'une vente (spec section 22) : quantity x current_price.
    Ce n'est PAS un profit (aucun coût de production n'est soustrait).
    """
    return quantity * current_price


def estimate_produce_value(product_info: dict, current_price: float) -> float:
    """
    Valeur brute estimée d'une production, basée sur le rendement maximum
    documenté (PRODUCTION_INFO). C'est une estimation optimiste (rendement
    maximal, pas garanti) et une valeur brute (pas un profit : le coût de
    graine n'est pas disponible ici de façon fiable, voir spec section 23).
    """
    return product_info["max_yield"] * current_price