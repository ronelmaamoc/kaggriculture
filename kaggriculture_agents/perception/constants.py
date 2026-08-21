"""
Constantes liées aux règles de Kaggriculture, utilisées par l'agent Perception.

Ces valeurs correspondent aux valeurs par défaut documentées dans README.md /
AGENTS.md. Comme elles sont configurables au niveau de l'épisode
(`env.configuration`) et ne sont PAS présentes dans `obs`, elles sont exposées
ici comme des valeurs par défaut que l'on peut surcharger explicitement à la
construction de `PerceptionAgent` si l'on connaît la config réelle de la partie.
"""

# --- Horizon de la partie (config, pas dans obs) --------------------------
DEFAULT_EPISODE_STEPS = 720   # episodeSteps par défaut (24 * 30)
DEFAULT_TURNS_PER_DAY = 24    # turnsPerDay par défaut
DEFAULT_SHED_CAPACITY = 100   # shedCapacity par défaut (hors graines)

# --- Vocabulaire du jeu (issu de README.md / AGENTS.md) -------------------
QUADRANTS = ("NW", "NE", "SW", "SE")

CROP_TYPES = frozenset({"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON"})
ANIMAL_TYPES = frozenset({"GOOSE", "COW", "SHEEP"})
ONGOING_CROPS = frozenset({"TOMATO", "STRAWBERRY"})  # production répétée
ONE_TIME_CROPS = frozenset({"WHEAT", "CARROT", "MELON"})

# Seuls WHEAT et FERTILIZER peuvent être rachetés au marché (BUY_PRODUCT).
MARKET_BUYABLE_PRODUCTS = frozenset({"WHEAT", "FERTILIZER"})

# Valeurs de `tile["kind"]`
TILE_KIND_PLANT = "PLANT"
TILE_KIND_WEED = "WEED"
TILE_KIND_COOP = "COOP"
TILE_KIND_PASTURE = "PASTURE"
ANIMAL_STRUCTURE_KINDS = frozenset({TILE_KIND_COOP, TILE_KIND_PASTURE})

TILE_LOCKED = "LOCKED"  # valeur brute (string) rencontrée dans tiles[y][x]

# Un côté (une plante / un animal) devient à risque dès qu'il a déjà manqué
# un jour d'arrosage/nourrissage : un deuxième jour manqué = perte définitive.
RISK_CONSECUTIVE_THRESHOLD = 1
