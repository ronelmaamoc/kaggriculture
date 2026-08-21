"""
Constantes du CriticAgent.

Convention de découplage (déjà en vigueur dans tout le projet, ex :
kaggriculture_agents/planner/constants.py, section "Le Planner ne relit PAS les
constantes internes de CropAgent...") : le CriticAgent NE RÉIMPORTE PAS
les constantes internes des autres agents (kaggriculture_agents/planner/constants.py y
compris). Il ne dépend que du CONTRAT PUBLIC qu'il évalue -- `FarmState`
(kaggriculture_agents/perception/models.py) et `Plan`/`PlanStep`
(kaggriculture_agents/planner/models.py) -- jamais des détails d'implémentation d'un
autre module. Les quelques tables ci-dessous décrivent donc, de façon
strictement locale et redondante par CONCEPTION (pas par oubli), le même
vocabulaire d'actions déjà utilisé par CropAgent / AnimalAgent / MarketAgent
/ PlannerAgent -- documenté dans README.md / AGENTS.md du jeu.
"""

# --- Sévérités (spec section 29) -------------------------------------------
SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_ERROR = "ERROR"
SEVERITY_CRITICAL = "CRITICAL"

SEVERITIES_BLOCKING_APPROVAL = frozenset({SEVERITY_ERROR, SEVERITY_CRITICAL})

# --- Vocabulaire d'actions attendu dans un Plan (spec sections 8-9) -------
# Reprend exactement les actions réellement proposées par CropAgent
# (kaggriculture_agents/crops/models.py), AnimalAgent (kaggriculture_agents/animals/models.py) et
# MarketAgent (kaggriculture_agents/market/models.py), telles que documentées dans leurs
# README respectifs.
ACTIONS_BY_SOURCE = {
    "crop": frozenset({"HARVEST", "WATER", "PLANT", "FERTILIZE", "DUG", "BUY_SEED"}),
    "animal": frozenset({"FEED", "CARE", "HARVEST", "COLLECT_FERTILIZER", "EXPANSION_OPPORTUNITY", "BUY_ANIMAL", "BUILD_COOP", "BUILD_PASTURE", "PLACE", "PICKUP", "DROP"}),
    "market": frozenset({"SELL", "HOLD", "PRODUCE"}),
    "investment": frozenset({"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "HIRE", "BUY_LAND", "PLACE", "BUILD_COOP", "BUILD_PASTURE"}),
}
KNOWN_SOURCE_AGENTS = frozenset(ACTIONS_BY_SOURCE.keys())

# --- Actions nécessitant qu'un worker soit physiquement sur une case ------
# (donc porteuses d'un `target` obligatoire ; symétrique de
# kaggriculture_agents/planner/constants.WORKER_REQUIRED_ACTIONS, redéfini localement --
# voir docstring du module).
WORKER_REQUIRED_ACTIONS = frozenset({
    "HARVEST", "WATER", "PLANT", "FERTILIZE", "DUG",
    "FEED", "CARE", "COLLECT_FERTILIZER", "EXPANSION_OPPORTUNITY",
    "PLACE", "BUILD_COOP", "BUILD_PASTURE", "PICKUP", "DROP",
})

# --- Actions marché : jamais de `target` (pas de position, spec MarketProposal) --
MARKET_ACTIONS = frozenset({"SELL", "HOLD", "PRODUCE", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "HIRE", "BUY_LAND"})

# --- Actions occupant EXCLUSIVEMENT une case (conflit de cible réel) ------
EXCLUSIVE_TARGET_ACTIONS = frozenset({"PLANT", "EXPANSION_OPPORTUNITY"})

# --- Ressources nommées de FarmState consommées par action (hors argent) --
# Fonction (PlanStep) -> nom de ressource dans le ledger local (voir
# analyzers.py). Une seule unité consommée par step (aucun PlanStep ne
# porte de champ "quantity").
def _seed_resource_key(step) -> str:
    return f"SEED_{step.product}"


RESOURCE_CONSUMPTION = {
    ("crop", "PLANT"): _seed_resource_key,
    ("crop", "FERTILIZE"): lambda step: "FERTILIZER",
    ("animal", "FEED"): lambda step: "WHEAT",
    ("animal", "PICKUP"): lambda step: f"ANIMAL_{step.product}",
    ("animal", "PLACE"): lambda step: f"INVENTORY_{step.product}",
}

# --- Argent réellement dépensé / réalisé à l'exécution d'un step ----------
# Même distinction que kaggriculture_agents/planner/constants.py : les ordres
# d'investissement engagent un débit immédiat ; seule SELL réalise un revenu
# immédiat.
CASH_CONSUMING_ACTIONS = frozenset({"EXPANSION_OPPORTUNITY", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "HIRE", "BUY_LAND"})
CASH_REALIZING_ACTIONS = frozenset({"SELL"})

# --- Pression sur le shed (spec section 26) --------------------------------
# Approximation volontaire, documentée : 1 unité de pression par step, même
# simplification que RESOURCE_CONSUMPTION (aucun PlanStep ne porte de champ
# "quantity"). HARVEST/COLLECT_FERTILIZER alimentent en réalité l'inventaire
# du worker, pas directement le shed (il faudrait un DROP) -- traité ici
# comme une pression potentielle si le plan les enchaîne jusqu'au shed.
SHED_PRESSURE_ACTIONS = frozenset({"HARVEST", "COLLECT_FERTILIZER"})
SHED_RELIEF_ACTIONS = frozenset({"SELL"})

# --- Correspondance animal -> produit vendable (README.md, table "Object
# Types" : Goose/Egg, Cow/Milk, Sheep/Wool). Dupliquée localement (voir
# docstring du module) plutôt que réimportée depuis kaggriculture_agents/animals/constants.py.
ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}

# --- Tolérances numériques (arrondis monétaires / flottants) --------------
FLOAT_TOLERANCE = 0.01
# Tolérance plus large pour les comparaisons agrégées (somme sur plusieurs
# steps) où de petits écarts d'arrondi individuels peuvent s'accumuler.
AGGREGATE_FLOAT_TOLERANCE = 1.0

# --- Poids de score (spec section 30) --------------------------------------
# score = 1.0 - somme des pénalités par issue, plafonné à [0, 1]. Le score
# est purement DIAGNOSTIC : il n'intervient jamais dans le calcul du statut
# (spec section 30, "les violations critiques doivent avoir priorité sur le
# score numérique" -- voir rules.py, qui décide le statut uniquement à
# partir des sévérités).
SEVERITY_SCORE_PENALTY = {
    SEVERITY_INFO: 0.0,
    SEVERITY_WARNING: 0.05,
    SEVERITY_ERROR: 0.20,
    SEVERITY_CRITICAL: 0.50,
}

# --- Pénalités de confiance (incertitude introduite par chaque issue) -----
SEVERITY_CONFIDENCE_PENALTY = {
    SEVERITY_INFO: 0.0,
    SEVERITY_WARNING: 0.02,
    SEVERITY_ERROR: 0.05,
    SEVERITY_CRITICAL: 0.10,
}
CONFIDENCE_PENALTY_CAP = 0.4

# --- Codes d'issue (évite les chaînes magiques dispersées, spec section 34) --
CODE_DUPLICATE_STEP_ID = "DUPLICATE_STEP_ID"
CODE_EMPTY_ACTION = "EMPTY_ACTION"
CODE_INVALID_PHASE = "INVALID_PHASE"
CODE_INVALID_PRIORITY = "INVALID_PRIORITY"

CODE_UNKNOWN_SOURCE_AGENT = "UNKNOWN_SOURCE_AGENT"
CODE_UNKNOWN_ACTION = "UNKNOWN_ACTION"

CODE_MISSING_TARGET = "MISSING_TARGET"
CODE_UNEXPECTED_TARGET = "UNEXPECTED_TARGET"
CODE_TARGET_LOCKED = "TARGET_LOCKED"

CODE_BUDGET_IMPOSSIBLE = "BUDGET_IMPOSSIBLE"
CODE_BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
CODE_RESOURCE_OVERUSE = "RESOURCE_OVERUSE"

CODE_WORKER_CAPACITY_EXCEEDED = "WORKER_CAPACITY_EXCEEDED"

CODE_DEPENDENCY_ORDER_INVALID = "DEPENDENCY_ORDER_INVALID"
CODE_MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
CODE_DEPENDENCY_CYCLE = "DEPENDENCY_CYCLE"

CODE_DUPLICATE_ACTION = "DUPLICATE_ACTION"
CODE_TARGET_CONFLICT = "TARGET_CONFLICT"

CODE_TIME_CONSTRAINT_VIOLATION = "TIME_CONSTRAINT_VIOLATION"

CODE_STORAGE_OVERFLOW = "STORAGE_OVERFLOW"

CODE_PROFIT_INCONSISTENT = "PROFIT_INCONSISTENT"
CODE_COST_EXCEEDS_REVENUE = "COST_EXCEEDS_REVENUE"
CODE_DOUBLE_COUNTED_PROFIT = "DOUBLE_COUNTED_PROFIT"