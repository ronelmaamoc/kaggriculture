"""
Constantes du PlannerAgent.

Le Planner ne relit PAS les constantes internes de CropAgent / AnimalAgent /
MarketAgent / EconomyAgent (spec section 68 : découplage, contrat public
uniquement). Les quelques tables ci-dessous ne dupliquent donc PAS les
tables métier (CROP_INFO, ANIMAL_INFO...) : elles décrivent uniquement des
faits propres à la PLANIFICATION (quelle action nécessite un worker, quelle
action consomme quelle ressource *nommée dans FarmState*), qui ne sont pas
portés par `EconomyProposal`.
"""

# --- Actions nécessitant qu'un worker soit physiquement sur la case -------
# Les actions marché (SELL/HOLD) sont soumises comme ordres indépendants du
# déplacement des workers (README.md, "Turn Processing Order" : les ordres
# marché sont une liste séparée des actions farmer/hand). PRODUCE n'apparaît
# jamais ici : c'est un doublon de PLANT, éliminé en amont par
# conflicts.deduplicate_proposals avant d'atteindre l'ordonnancement.
WORKER_REQUIRED_ACTIONS = frozenset({
    "HARVEST", "WATER", "PLANT", "FERTILIZE", "DUG",
    "FEED", "CARE", "COLLECT_FERTILIZER", "EXPANSION_OPPORTUNITY",
    "PLACE", "BUILD_COOP", "BUILD_PASTURE", "PICKUP", "DROP",
})

# --- Actions occupant EXCLUSIVEMENT une case (conflit de cible) -----------
# Deux propositions différentes visant la même case pour l'une de ces
# actions ne peuvent pas être toutes les deux retenues (une case ne peut
# porter qu'une seule culture / qu'un seul animal à la fois).
EXCLUSIVE_TARGET_ACTIONS = frozenset({"PLANT", "EXPANSION_OPPORTUNITY"})

# Les investissements sont des ordres marché et ne consomment pas de worker.
MARKET_ORDER_ACTIONS = frozenset({"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL", "HIRE", "BUY_LAND"})

# --- Actions purement informationnelles, jamais planifiées comme un step --
# HOLD ("ne pas vendre maintenant") ne correspond à aucune action
# Kaggriculture exécutable : c'est une recommandation de ne rien faire.
NON_ACTIONABLE_ACTIONS = frozenset({"HOLD"})

# --- Ressources FarmState consommées par action (hors argent) -------------
# Fonction (EconomyProposal) -> nom de ressource dans le ledger (voir
# resources.py). Une seule unité consommée par step dans cette v1 (aucune
# proposition actuelle ne porte de champ "quantity" pour les actions
# consommant une ressource nommée).
def _seed_resource_key(ep) -> str:
    return f"SEED_{ep.product}"


RESOURCE_CONSUMPTION = {
    ("crop", "PLANT"): _seed_resource_key,
    ("crop", "FERTILIZE"): lambda ep: "FERTILIZER",
    ("animal", "FEED"): lambda ep: "WHEAT",
    ("animal", "PICKUP"): lambda ep: f"ANIMAL_{ep.product}",
    ("animal", "PLACE"): lambda ep: f"INVENTORY_{ep.product}",
}

# --- Argent réellement dépensé à l'exécution du step -----------------------
# Distinction importante (documentée en détail dans README.md, section
# "Limites / incohérences héritées") : `EconomyProposal.cost` pour PLANT et
# FERTILIZE représente la valeur d'une ressource DÉJÀ POSSÉDÉE (graine ou
# fertilisant en stock, condition vérifiée par CropAgent.rules avant même de
# proposer l'action) — ce n'est PAS une dépense monétaire nouvelle. Seule
# EXPANSION_OPPORTUNITY (achat d'un animal) engage un débit réel immédiat.
CASH_CONSUMING_ACTIONS = frozenset({"EXPANSION_OPPORTUNITY", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "HIRE", "BUY_LAND"})

# --- Actions qui réalisent un revenu monétaire IMMÉDIAT --------------------
# HARVEST produit de l'inventaire, pas de l'argent : seule une vente
# effective (SELL) convertit un produit en trésorerie le même tour.
CASH_REALIZING_ACTIONS = frozenset({"SELL"})

# --- Poids du score de plan (documentés, simples, modifiables) ------------
# plan_score = W_PROFIT * profit_norm + W_URGENCY * avg_urgency
#              - W_RISK * avg_risk
# Version v1 volontairement simple (spec section 29) : `strategic_value` et
# `idle_time` ne sont pas modélisés (aucune donnée fiable disponible dans
# FarmState pour les estimer sans inventer des hypothèses).
W_PROFIT = 0.55
W_URGENCY = 0.25
W_RISK = 0.20

PROFIT_NORMALIZATION_CAP = 2000.0

# --- Sélection gloutonne : ordre de priorité des propositions prêtes ------
# (spec section 47 : "trier par priorité"). economic_score est déjà la
# synthèse produite par EconomyAgent ; on ne le recalcule pas, on l'utilise
# comme clé primaire, avec des critères secondaires déterministes.
def selection_key(ep):
    return (-ep.economic_score, -ep.urgency, ep.risk)


# --- Confiance du plan ------------------------------------------------------
# Pénalité appliquée à la confiance moyenne des steps retenus par
# proposition rejetée (données incomplètes / contraintes non satisfaites,
# spec section 55), plafonnée pour ne jamais tomber à 0 uniquement à cause
# du nombre de rejets.
CONFIDENCE_PENALTY_PER_REJECTION = 0.02
CONFIDENCE_PENALTY_CAP = 0.3