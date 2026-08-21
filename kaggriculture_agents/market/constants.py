"""
Constantes du MarketAgent.

MARKET_PRODUCT_INFO reprend TEL QUEL le tableau "The Price Function" de
README.md (colonne "Base"). C'est le prix théorique du marché quand son
inventaire vaut exactement `I0` (équilibre), donc une référence stable et
documentée par le jeu lui-même — PAS une valeur inventée par cet agent.

PRODUCTION_INFO reprend TEL QUEL le sous-ensemble utile du tableau "Object
Types" (colonnes Time to First Yield / Max Yield) déjà dupliqué par
kaggriculture_agents/crops/constants.py, restreint aux produits végétaux (les seuls sur
lesquels le MarketAgent peut raisonner sans dépendre de l'état des
structures d'élevage, qu'il n'observe pas).

Ces deux tables ne varient pas d'une partie à l'autre, contrairement aux
prix courants et à l'inventaire du marché, qui eux viennent de `FarmState`.
"""


# Paramètres de la courbe de prix réelle du jeu (README.md, section Price Function).
# Ils permettent au MarketAgent de projeter le prix à +1/+3/+7 jours au lieu de
# réagir uniquement au prix courant. I0 et T sont les calibrations documentées.
MARKET_CURVE_PARAMS = {
    "WHEAT": {"base": 25.0, "I0": 10000.0, "T": 400.0, "below_func": "sqrt", "below_target": 0.80, "above_func": "log", "above_target": 0.20},
    "CARROT": {"base": 35.0, "I0": 10000.0, "T": 450.0, "below_func": "log", "below_target": 0.20, "above_func": "sqrt", "above_target": 0.70},
    "TOMATO": {"base": 60.0, "I0": 10000.0, "T": 200.0, "below_func": "linear", "below_target": 0.40, "above_func": "sqrt", "above_target": 0.60},
    "STRAWBERRY": {"base": 120.0, "I0": 10000.0, "T": 100.0, "below_func": "sqrt", "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON": {"base": 250.0, "I0": 10000.0, "T": 300.0, "below_func": "log", "below_target": 0.20, "above_func": "sq", "above_target": 3.60},
    "EGG": {"base": 50.0, "I0": 10000.0, "T": 332.0, "below_func": "linear", "below_target": 0.40, "above_func": "log", "above_target": 0.20},
    "MILK": {"base": 160.0, "I0": 10000.0, "T": 122.0, "below_func": "sqrt", "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL": {"base": 200.0, "I0": 10000.0, "T": 105.0, "below_func": "log", "below_target": 0.20, "above_func": "sq", "above_target": 3.20},
    "FERTILIZER": {"base": 100.0, "I0": 10000.0, "T": 200.0, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}

MARKET_PRODUCT_INFO = {
    "WHEAT": {"base_price": 25},
    "CARROT": {"base_price": 35},
    "TOMATO": {"base_price": 60},
    "STRAWBERRY": {"base_price": 120},
    "MELON": {"base_price": 250},
    "EGG": {"base_price": 50},
    "MILK": {"base_price": 160},
    "WOOL": {"base_price": 200},
    "FERTILIZER": {"base_price": 100},
}

# Produits végétaux "plantables" pour lesquels une PRODUCE_OPPORTUNITY peut
# être évaluée (le MarketAgent n'observe pas les parcelles ni les structures
# d'élevage : il ne peut donc pas savoir si une nouvelle culture/animal est
# réellement plaçable, seulement si le prix + le temps restant la rendent
# intéressante EN PRINCIPE).
PRODUCTION_INFO = {
    "WHEAT": {"first_yield_day": 2, "max_yield": 6},
    "CARROT": {"first_yield_day": 2, "max_yield": 4},
    "TOMATO": {"first_yield_day": 8, "max_yield": 4},
    "STRAWBERRY": {"first_yield_day": 10, "max_yield": 4},
    "MELON": {"first_yield_day": 10, "max_yield": 6},
}

# --- Position du prix courant par rapport au prix de base (base = 1.0) -----
# normalized_price = current_price / base_price
# 1.0 = prix exactement au prix de base (inventaire marché == I0)
# < 1.0 = marché en surplus (glut, prix en baisse)
# > 1.0 = marché en pénurie (scarcity, prix en hausse)
PRICE_LOW_THRESHOLD = 0.85
PRICE_HIGH_THRESHOLD = 1.15

# Borne utilisée uniquement pour normaliser normalized_price dans [0, 1]
# avant pondération dans le score (voir scoring.py). Un prix multiplié par 2
# par rapport à sa base est déjà un cas très favorable pour la plupart des
# produits (cf. table README : P(I0-T) dépasse rarement 2x le prix de base).
PRICE_POSITION_NORMALIZATION_CAP = 2.0

# --- Priorités générales des types d'action (référence, non un score) -----
ACTION_PRIORITY = {
    "SELL_HIGH": 0.9,
    "SELL_NORMAL": 0.6,
    "PRODUCE": 0.5,
    "HOLD": 0.3,
}

# --- Poids du scoring SELL / HOLD (documentés, simples, modifiables) -------
# score_sell   = W_PRICE_SELL   * price_score + W_VALUE_SELL   * value_norm + W_INVENTORY * inventory_norm
# score_hold   = W_PRICE_HOLD   * (1 - price_score) + W_INVENTORY_HOLD * inventory_norm
# score_produce= W_PRICE_PRODUCE* price_score + W_VALUE_PRODUCE* value_norm + W_TIME * time_score
W_PRICE_SELL = 0.5
W_VALUE_SELL = 0.3
W_INVENTORY_SELL = 0.2

W_PRICE_HOLD = 0.7
W_INVENTORY_HOLD = 0.3

W_PRICE_PRODUCE = 0.45
W_VALUE_PRODUCE = 0.30
W_TIME_PRODUCE = 0.25

# --- Bornes de normalisation (0..1) ----------------------------------------
# Pire cas de vente : shed_capacity par défaut (100, voir
# kaggriculture_agents/perception/constants.DEFAULT_SHED_CAPACITY) * prix le plus élevé
# possible en pénurie forte (~2x MELON base = 500).
VALUE_NORMALIZATION_CAP = 100 * 500
# Inventaire de référence pour normaliser une quantité en stock : la
# capacité par défaut du shed (hors graines).
INVENTORY_NORMALIZATION_CAP = 100

# --- Urgence par défaut ------------------------------------------------
SELL_URGENCY_DEFAULT = 0.4
HOLD_URGENCY_DEFAULT = 0.2
PRODUCE_URGENCY_DEFAULT = 0.25

# Bonus d'urgence si le shed est proche de sa capacité (state.risks) ou si la
# partie touche à sa fin (state.time) : dans les deux cas, conserver le stock
# devient moins pertinent (section 29-30 de la spec).
SELL_URGENCY_SHED_NEAR_CAPACITY = 0.85
SELL_URGENCY_END_OF_GAME = 0.9

# "Fin de partie" = il reste moins d'un jour de jeu (voir README.md,
# turnsPerDay par défaut = 24 ; state.time.remaining_days est déjà calculé
# par PerceptionAgent, donc pas de constante de tours dupliquée ici).
END_OF_GAME_REMAINING_DAYS = 1