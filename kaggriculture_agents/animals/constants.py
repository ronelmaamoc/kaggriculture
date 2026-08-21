"""
Constantes de l'AnimalAgent.

ANIMAL_INFO reprend TEL QUEL le tableau "Object Types" et le tableau "Price
Function" de README.md (colonnes Seed Cost -> purchase_cost, Base Market
Price -> base_price du produit, Time to First Yield -> first_yield_day,
Max Yield -> max_held). Ce ne sont pas des valeurs inventées : elles sont
documentées par le jeu lui-même, et ne varient pas d'une partie à l'autre
(contrairement aux prix de marché courants, qui eux viennent de `FarmState`).

`structure_kind` = la structure sur laquelle l'animal peut être placé
(COOP pour GOOSE, PASTURE pour COW/SHEEP), documentée dans README.md
section "Actions > Animals > PLACE".
"""

ANIMAL_INFO = {
    "GOOSE": {
        "structure_kind": "COOP",
        "product": "EGG",
        "purchase_cost": 300, "base_price": 50,
        "first_yield_day": 4, "max_held": 4,
    },
    "COW": {
        "structure_kind": "PASTURE",
        "product": "MILK",
        "purchase_cost": 400, "base_price": 160,
        "first_yield_day": 8, "max_held": 6,
    },
    "SHEEP": {
        "structure_kind": "PASTURE",
        "product": "WOOL",
        "purchase_cost": 500, "base_price": 200,
        "first_yield_day": 6, "max_held": 6,
    },
}

# Quels animaux peuvent occuper quelle structure vide (README.md, PLACE).
STRUCTURE_TO_ANIMALS = {
    "COOP": ["GOOSE"],
    "PASTURE": ["COW", "SHEEP"],
}

# Ressource consommée par FEED (README.md : "All animals must be fed every
# day using wheat").
FEED_RESOURCE = "WHEAT"

# --- Priorités générales des types d'action (référence, non un score) -----
# FEED est scindé en deux niveaux : un animal déjà en retard d'un jour
# (at_risk == True, cf. PerceptionAgent) risque de s'échapper au prochain
# jour manqué, contrairement à un animal simplement pas-encore-nourri
# aujourd'hui.
ACTION_PRIORITY = {
    "FEED_CRITICAL": 1.0,
    "HARVEST": 0.9,
    "COLLECT_FERTILIZER": 0.6,
    "CARE": 0.55,
    "FEED_NORMAL": 0.8,
    "EXPANSION_OPPORTUNITY": 0.3,
}

# --- Poids du scoring (documentés, simples, modifiables) ------------------
# score = W_URGENCY*urgency + W_VALUE*value_norm + W_RISK*risk
#         - W_COST*cost_norm - W_DISTANCE*distance_norm
# Mêmes poids que CropAgent (kaggriculture_agents/crops/constants.py) pour que les scores
# des deux agents restent comparables une fois un Coordinator introduit.
W_URGENCY = 0.35
W_VALUE = 0.30
W_RISK = 0.20
W_COST = 0.10
W_DISTANCE = 0.05

# --- Bornes de normalisation (0..1) ----------------------------------------
# Le pire cas de valeur en jeu est celui d'un FEED critique sur un SHEEP :
# purchase_cost (500) + max_held (6) * base_price (200) = 1700.
VALUE_NORMALIZATION_CAP = 1700
COST_NORMALIZATION_CAP = 500        # achat animal le plus cher (Sheep)
DISTANCE_NORMALIZATION_CAP = 20     # ~2 * boardSize par défaut (10)

# --- Urgences par défaut (documentées, simples) -----------------------------
FEED_URGENCY_CRITICAL = 0.97   # consecutive_unfed >= 1 : un jour de plus = perte définitive
FEED_URGENCY_NORMAL = 0.5      # pas encore nourri aujourd'hui, mais pas encore à risque

HARVEST_URGENCY_DEFAULT = 0.6  # pas de décroissance documentée pour la production animale

CARE_URGENCY_DEFAULT = 0.35    # bénéfice différé (bonus banqué), jamais critique

FERTILIZER_URGENCY_DEFAULT = 0.3  # pas de risque de perte (ne s'accumule pas, mais ne périme pas non plus)

EXPANSION_URGENCY_DEFAULT = 0.15  # opportunité, jamais urgente