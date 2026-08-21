"""
Constantes de l'EconomyAgent.

CROP_SEED_COST / CROP_FIRST_YIELD_DAY et ANIMAL_PURCHASE_COST /
ANIMAL_FIRST_YIELD_DAY / ANIMAL_PRODUCT reprennent TEL QUEL les
sous-ensembles utiles des tableaux "Object Types" de README.md déjà
dupliqués par kaggriculture_agents/crops/constants.py et kaggriculture_agents/animals/constants.py.
Ce ne sont pas des valeurs inventées : l'EconomyAgent ne reçoit PAS le coût
réel d'une action depuis les propositions spécialisées (CropProposal /
AnimalProposal / MarketProposal ne portent pas de champ `cost`), il doit
donc pouvoir le retrouver lui-même à partir de données documentées, de la
même façon que les autres modules le font déjà chacun de leur côté.

Ces tables ne varient pas d'une partie à l'autre, contrairement à
`state.resources.money`, qui lui vient de `FarmState`.
"""

CROP_SEED_COST = {
    "WHEAT": 10,
    "CARROT": 20,
    "TOMATO": 50,
    "STRAWBERRY": 100,
    "MELON": 80,
}
CROP_FIRST_YIELD_DAY = {
    "WHEAT": 2,
    "CARROT": 2,
    "TOMATO": 8,
    "STRAWBERRY": 10,
    "MELON": 10,
}

ANIMAL_PURCHASE_COST = {
    "GOOSE": 300,
    "COW": 400,
    "SHEEP": 500,
}
ANIMAL_FIRST_YIELD_DAY = {
    "GOOSE": 4,
    "COW": 8,
    "SHEEP": 6,
}
# Produit associé à chaque animal (README.md, table "Object Types") : sert
# uniquement à relier une AnimalProposal HARVEST à une MarketProposal SELL
# du même produit (détection de dépendance, spec section 54-55).
ANIMAL_PRODUCT = {
    "GOOSE": "EGG",
    "COW": "MILK",
    "SHEEP": "WOOL",
}

# --- Budget --------------------------------------------------------------
# safe_budget = money - (money * RESERVE_RATIO)
# Une ferme ne doit pas engager toute sa trésorerie immédiatement (spec
# sections 10-11). Valeur par défaut documentée ici, modifiable si le
# projet définit une politique budgétaire différente ailleurs.
RESERVE_RATIO = 0.20

# Une seule proposition ne devrait normalement pas engager plus d'une
# certaine part du budget sécurisé (spec section 23, exemple investment=900
# sur money=1000 jugé risqué).
SAFE_INVESTMENT_MAX_SHARE = 0.5

# --- Ressources critiques (spec section 12-13) ----------------------------
SEED_CRITICAL_THRESHOLD = 0     # aucune graine du type = CRITICAL
SEED_LIMITED_THRESHOLD = 3      # <= 3 graines = LIMITED

FEED_CRITICAL_THRESHOLD = 0     # aucun WHEAT en shed = CRITICAL (risque pour les animaux)
FEED_LIMITED_THRESHOLD = 10

FERTILIZER_CRITICAL_THRESHOLD = 0
FERTILIZER_LIMITED_THRESHOLD = 2

# Produits pour lesquels une vente est pénalisée si la ressource est
# CRITICAL (spec section 13 : ne pas aggraver une pénurie déjà critique).
CRITICAL_SELL_PENALTY_PRODUCTS = ("WHEAT", "FERTILIZER")
CRITICAL_SELL_RISK_FLOOR = 0.8

# --- Poids du score économique (documentés, simples, modifiables) ---------
# economic_score = W_PROFIT*profit_norm + W_ROI*roi_norm + W_LIQUIDITY*liquidity_score
#                 + W_URGENCY*urgency + W_RESOURCE*resource_norm - W_RISK*risk
# Score forcé à 0 si l'action n'est pas jouable dans le temps restant
# (time_feasible == False, spec section 34-35).
W_PROFIT = 0.30
W_ROI = 0.20
W_LIQUIDITY = 0.15
W_URGENCY = 0.15
W_RESOURCE = 0.10
W_RISK = 0.10

# --- Bornes de normalisation (0..1) ----------------------------------------
# Cas favorable documenté dans la spec (section 28) : profit=130, ROI=2.6
# pour une action jugée "très intéressante". On prend des bornes larges
# pour rester cohérent avec les valeurs de marché réelles (MELON ~ 250-400$).
PROFIT_NORMALIZATION_CAP = 2000.0
ROI_NORMALIZATION_CAP = 3.0
CASH_DELTA_CAP = 2000.0
RESOURCE_EFFICIENCY_NORMALIZATION_CAP = 10.0

# --- Conflit budgétaire (spec section 31-32) ------------------------------
# Pénalité multiplicative appliquée au score d'une proposition dont le coût
# ferait dépasser le budget sécurisé une fois les propositions plus
# intéressantes déjà "réservées" (voir agent.py._apply_budget_conflicts).
BUDGET_CONFLICT_PENALTY = 0.5