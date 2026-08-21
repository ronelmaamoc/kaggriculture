"""Prévision déterministe de la demande du marché.

La demande est déduite de trois signaux observables :
1) boutiques débloquées et leur nombre (consommation récurrente),
2) consommation du centre-ville (1 unité/jour hors fertilisant),
3) production publique imminente de l'adversaire.

Ce module ne lit aucun RNG et ne modifie jamais l'état.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

# Poids relatifs de demande par boutique. Les valeurs représentent des unités
# de pression de demande, pas des prix inventés.
SHOP_DEMAND: Dict[str, Dict[str, float]] = {
    "BAKERY": {"EGG": 1.0, "WHEAT": 1.0},
    "PIZZA_SHOP": {"MILK": 1.0, "TOMATO": 1.0, "WHEAT": 1.0},
    "BRUNCH_SPOT": {"EGG": 1.0, "WHEAT": 1.0, "STRAWBERRY": 1.0},
    "YARN_STORE": {"WOOL": 2.0},
    "ICE_CREAM_SHOP": {"STRAWBERRY": 1.0, "MILK": 1.0, "WHEAT": 1.0},
    "PET_CAFE": {"CARROT": 2.0},
    "SMOOTHIE_SHOP": {"STRAWBERRY": 1.0, "MILK": 1.0},
    "FARMERS_MARKET": {"WHEAT": 1.0, "CARROT": 1.0, "TOMATO": 1.0, "STRAWBERRY": 1.0},
}

BASE_PRODUCTS = {
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
}

# Durées du premier rendement : utiles pour projeter la production adverse.
FIRST_YIELD = {"WHEAT": 2, "CARROT": 2, "TOMATO": 8, "STRAWBERRY": 10, "MELON": 10,
               "EGG": 4, "MILK": 8, "WOOL": 6}

# Production moyenne prudente utilisée uniquement pour la pression future.
AVG_YIELD = {"WHEAT": 3, "CARROT": 2, "TOMATO": 2, "STRAWBERRY": 2, "MELON": 3,
             "EGG": 2, "MILK": 3, "WOOL": 3}


@dataclass(frozen=True)
class DemandForecast:
    demand_units: Dict[str, float]
    shop_counts: Dict[str, int]
    opponent_supply_pressure: Dict[str, float]
    scarcity: Dict[str, float]
    expected_price_factor: Dict[str, float]


def build_demand_forecast(state) -> DemandForecast:
    counts = dict(sorted(state.town.shop_counts.items()))
    demand = {p: 1.0 for p in BASE_PRODUCTS if p != "FERTILIZER"}  # centre-ville: 1/jour
    for shop, count in counts.items():
        for product, weight in SHOP_DEMAND.get(shop, {}).items():
            demand[product] = demand.get(product, 0.0) + float(count) * weight

    # Pression de production adverse : l'état public donne le nombre de
    # plantes/animaux, pas leur contenu privé. On reste conservateur.
    opponent: Dict[str, float] = {p: 0.0 for p in BASE_PRODUCTS}
    planted = max(0, int(state.opponent.planted_crop_count))
    animals = max(0, int(state.opponent.animal_count))
    # Répartition déterministe : on ne devine pas les types cachés.
    if planted:
        for product in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"):
            opponent[product] += planted * AVG_YIELD[product] / 5.0
    if animals:
        for product in ("EGG", "MILK", "WOOL"):
            opponent[product] += animals * AVG_YIELD[product] / 3.0

    scarcity: Dict[str, float] = {}
    price_factor: Dict[str, float] = {}
    for product in sorted(BASE_PRODUCTS):
        inv = float(state.market.inventory.get(product, 10000.0))
        current = float(state.market.prices.get(product, 0.0))
        base = _base_price(product)
        # Le gap d'inventaire est le signal de rareté structurelle. La demande
        # quotidienne et l'offre adverse déterminent le drift à court terme.
        inventory_gap = (10000.0 - inv) / 10000.0
        net_daily = demand.get(product, 0.0) - opponent.get(product, 0.0)
        flow_pressure = max(-0.25, min(0.25, net_daily / 100.0))
        s = max(-1.0, min(1.0, 2.0 * inventory_gap + flow_pressure))
        scarcity[product] = s
        if base > 0:
            current_factor = current / base
            price_factor[product] = max(0.5, min(2.5, current_factor * (1.0 + 0.20 * s)))
        else:
            price_factor[product] = 1.0

    return DemandForecast(
        demand_units=dict(sorted(demand.items())),
        shop_counts=counts,
        opponent_supply_pressure=dict(sorted(opponent.items())),
        scarcity=dict(sorted(scarcity.items())),
        expected_price_factor=dict(sorted(price_factor.items())),
    )


def _base_price(product: str) -> float:
    return {
        "WHEAT": 25.0, "CARROT": 35.0, "TOMATO": 60.0, "STRAWBERRY": 120.0,
        "MELON": 250.0, "EGG": 50.0, "MILK": 160.0, "WOOL": 200.0,
        "FERTILIZER": 100.0,
    }.get(product, 0.0)


def demand_score(forecast: DemandForecast, product: str) -> float:
    """Pression de demande normalisée : demande + rareté, bornée 0..1."""
    demand = forecast.demand_units.get(product, 0.0)
    max_demand = max(forecast.demand_units.values(), default=1.0)
    d = demand / max(1.0, max_demand)
    scarcity = (forecast.scarcity.get(product, 0.0) + 1.0) / 2.0
    return max(0.0, min(1.0, 0.65 * d + 0.35 * scarcity))
