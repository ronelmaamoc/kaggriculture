"""
Constantes de l'ExecutorAgent.

Découplage (même convention que tout le projet, voir
kaggriculture_agents/critic/constants.py et kaggriculture_agents/coordinator/README.md,
"Découplage (duck-typing strict)") : ce module ne réimporte AUCUNE
constante interne de kaggriculture_agents/coordinator ni de kaggriculture_agents/planner. Le seul
champ d'un autre agent comparé ici est `schedule.status.value`, en pur
duck-typing contre une valeur locale (voir agent.py), jamais l'enum
`ScheduleStatus` importée.

DÉCOUVERTE IMPORTANTE (spec section 4 : "inspecter le code existant pour
déterminer exactement comment l'agent principal communique avec
Kaggriculture avant d'implémenter") : il n'existe, nulle part dans ce
projet, d'objet "environnement" appelable en cours de partie. La SEULE
interface réelle avec Kaggriculture est la fonction `agent(obs) -> dict`
elle-même (voir kaggriculture_agents/coordinator/README.md, exemple d'utilisation) :
Kaggriculture appelle cette fonction UNE FOIS PAR TOUR, avec la nouvelle
observation, et attend en retour un dictionnaire
`{"farmer": [...], "hands": [[...], ...], "market": [[...], ...]}`
couvrant TOUT ce tour — il n'y a pas de retour synchrone "action par
action" (pas de `reward`/`turn`/`state` immédiat par action individuelle).
Ce module est donc conçu autour de cette contrainte réelle plutôt que
d'inventer une API `env.step()` de type Gym qui n'existe pas ici (voir
README.md du module pour le détail de cette adaptation).
"""

# --- Vocabulaire d'actions Kaggriculture réellement mappable -------------
# (README.md du jeu, sections "Plants" / "Animals" / "Market Action").
# Toutes les autres actions du Plan (HOLD, PRODUCE) sont déjà éliminées
# avant d'atteindre le Plan/ExecutionSchedule (voir
# kaggriculture_agents/planner/constants.NON_ACTIONABLE_ACTIONS et le commentaire sur
# PRODUCE dans ce même fichier) : l'ExecutorAgent ne les revoit jamais.
SIMPLE_WORKER_ACTIONS = {
    "WATER": ("WATER",),
    "HARVEST": ("HARVEST",),
    "FERTILIZE": ("FERTILIZE",),
    "DUG": ("DIG",),
    "FEED": ("FEED",),
    "CARE": ("CARE",),
    "COLLECT_FERTILIZER": ("COLLECT_FERTILIZER",),
    "PICKUP": ("PICKUP",),
    "DROP": ("DROP",),
}
PLANT_ACTION = "PLANT"          # nécessite le produit : ("PLANT", product)
MARKET_SELL_ACTION = "SELL"     # ordre marché : ["SELL", product, quantity]
MARKET_ORDER_ACTIONS = frozenset({"SELL", "BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "HIRE", "BUY_LAND"})

# --- Actions non exécutables en l'état ------------------------------------
# EXPANSION_OPPORTUNITY est une opportunité analytique ; la chaîne exécutable
# est produite par AnimalAgent sous la forme BUILD_* + BUY_ANIMAL + PLACE.
UNSUPPORTED_ACTIONS = frozenset({"EXPANSION_OPPORTUNITY"})

# --- Quantité de vente par défaut ------------------------------------------
# Ni PlanStep ni ExecutionStep ne portent de champ "quantity" (même
# simplification déjà assumée par kaggriculture_agents/critic/constants.py,
# SHED_PRESSURE_ACTIONS : 1 unité par step). Documenté comme limite connue.
DEFAULT_SELL_QUANTITY = 1

# --- Déplacement ------------------------------------------------------------
# Un worker Kaggriculture ne peut faire qu'UNE seule action par tour
# (README.md, "Each Farmer / Farm Hand can be given an action every turn") :
# se déplacer ET agir le même tour est impossible. Si le worker affecté par
# le CoordinatorAgent n'est pas déjà sur la case cible, l'ExecutorAgent émet
# UN SEUL pas de déplacement vers la cible au lieu de l'action prévue ; le
# pipeline complet étant rejoué à chaque tour (voir kaggriculture_agents/coordinator/README.md,
# "Limites actuelles"), l'action prévue sera reproposée automatiquement au
# tour suivant une fois le worker arrivé. Convention de repère LOCALE et non
# vérifiée ailleurs dans le projet (aucun autre module n'en a eu besoin) :
# x croissant = EAST, y croissant = SOUTH.
MOVE_NORTH, MOVE_SOUTH, MOVE_EAST, MOVE_WEST = "NORTH", "SOUTH", "EAST", "WEST"
PASS_ACTION = ("PASS",)

# --- Codes d'échec (spec section 7) ----------------------------------------
CODE_ACTION_REJECTED = "ACTION_REJECTED"
CODE_INVALID_TARGET = "INVALID_TARGET"
CODE_INSUFFICIENT_RESOURCE = "INSUFFICIENT_RESOURCE"
CODE_WORKER_UNAVAILABLE = "WORKER_UNAVAILABLE"
CODE_ENVIRONMENT_ERROR = "ENVIRONMENT_ERROR"
CODE_INVALID_ACTION = "INVALID_ACTION"
CODE_UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
CODE_ENVIRONMENT_DISCONNECTED = "ENVIRONMENT_DISCONNECTED"
CODE_INVALID_ENVIRONMENT_STATE = "INVALID_ENVIRONMENT_STATE"

# Erreurs après lesquelles poursuivre l'exécution du reste du tour n'a pas
# de sens (spec section 17) : on arrête proprement, le reste des steps dus
# ce tour est marqué SKIPPED (reason=ENGINE_STOPPED).
NON_RECOVERABLE_CODES = frozenset({
    CODE_ENVIRONMENT_ERROR, CODE_ENVIRONMENT_DISCONNECTED, CODE_INVALID_ENVIRONMENT_STATE,
})

# --- Codes de skip (spec section 19) ---------------------------------------
REASON_DEPENDENCY_FAILED = "DEPENDENCY_FAILED"
REASON_PREVIOUS_PHASE_FAILED = "PREVIOUS_PHASE_FAILED"
REASON_RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"
REASON_BLOCKED = "BLOCKED"
REASON_FUTURE_TURN = "FUTURE_TURN"          # step programmé pour un tour ultérieur (voir agent.py)
REASON_ENGINE_STOPPED = "ENGINE_STOPPED"    # arrêt après échec non récupérable (spec section 17)
REASON_ALREADY_EXECUTED = "ALREADY_EXECUTED"  # idempotence (spec section 26)

# --- Statut du schedule à ne jamais exécuter (duck-typing, voir agent.py) --
BLOCKED_SCHEDULE_STATUS_VALUE = "blocked"

# --- Action neutre par défaut, envoyée à Kaggriculture pour tout worker ---
# sans step dû ce tour (README.md, "PASS — Default if there is nothing to do").
DEFAULT_TURN_ACTIONS = {"farmer": ["PASS"], "hands": [], "market": []}
