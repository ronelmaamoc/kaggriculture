"""
Constantes du CropAgent.

CROP_INFO reprend TEL QUEL le tableau "Object Types" de README.md (colonnes
Seed Cost / Base Market Price / Time to First Yield / Time to Max Yield /
Max Yield / Yield Type). Ce ne sont pas des valeurs inventées : elles sont
documentées par le jeu lui-même, et ne varient pas d'une partie à l'autre
(contrairement aux prix de marché courants, qui eux viennent de `FarmState`).

`bonus_watering_start` = ceil(max_yield_day / 2), tel que documenté dans la
section "Harvest Yields" de README.md pour les cultures "one-time".
"""

import math

CROP_INFO = {
    "WHEAT": {
        "seed_cost": 10, "base_price": 25,
        "first_yield_day": 2, "max_yield_day": 4, "max_yield": 6,
        "is_ongoing": False,
    },
    "CARROT": {
        "seed_cost": 20, "base_price": 35,
        "first_yield_day": 2, "max_yield_day": 3, "max_yield": 4,
        "is_ongoing": False,
    },
    "TOMATO": {
        "seed_cost": 50, "base_price": 60,
        "first_yield_day": 8, "max_yield_day": 11, "max_yield": 4,
        "is_ongoing": True,
    },
    "STRAWBERRY": {
        "seed_cost": 100, "base_price": 120,
        "first_yield_day": 10, "max_yield_day": 16, "max_yield": 4,
        "is_ongoing": True,
    },
    "MELON": {
        "seed_cost": 80, "base_price": 250,
        "first_yield_day": 10, "max_yield_day": 10, "max_yield": 6,
        "is_ongoing": False,
    },
}
for _info in CROP_INFO.values():
    _info["bonus_watering_start"] = math.ceil(_info["max_yield_day"] / 2)

FERTILIZER_BASE_PRICE = 100  # README, table "Object Types", ligne Fertilizer

# --- Priorités générales des types d'action (référence, non un score) -----
ACTION_PRIORITY = {
    "HARVEST": 4,
    "WATER": 3,
    "FERTILIZE": 2,
    "PLANT": 1,
}

# --- Poids du scoring (documentés, simples, modifiables) ------------------
# score = W_URGENCY*urgency + W_VALUE*value_norm + W_RISK*risk
#         - W_COST*cost_norm - W_DISTANCE*distance_norm
W_URGENCY = 0.35
W_VALUE = 0.30
W_RISK = 0.20
W_COST = 0.10
W_DISTANCE = 0.05

# --- Bornes de normalisation (0..1) ----------------------------------------
VALUE_NORMALIZATION_CAP = 6 * 250   # yield max (Melon=6) * prix de base le + élevé
COST_NORMALIZATION_CAP = 100        # coût de graine le plus élevé (Strawberry)
DISTANCE_NORMALIZATION_CAP = 20     # ~2 * boardSize par défaut (10)

# --- Urgences par défaut (documentées, simples) ----------------------------
HARVEST_URGENCY_DECAYING = 1.0
HARVEST_URGENCY_READY = 0.6

WATER_URGENCY_AT_RISK = 0.95
WATER_URGENCY_NORMAL = 0.5

PLANT_URGENCY_DEFAULT = 0.3
FERTILIZE_URGENCY_DEFAULT = 0.4

FERTILIZE_BONUS_DAYS = 3
FERTILIZE_ONE_TIME_EXTRA_UNITS_PER_DAY = 1
FERTILIZE_ONGOING_EXTRA_UNITS = 1


WEED_URGENCY_DEFAULT = 0.88
WEED_SCORE_DEFAULT = 0.90
