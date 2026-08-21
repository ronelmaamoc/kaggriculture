"""
Constantes du CoordinatorAgent.

Convention de découplage déjà en vigueur dans tout le projet (voir
kaggriculture_agents/critic/agent.py, kaggriculture_agents/planner/agent.py) : AUCUN agent n'importe
les modules internes -- ni même les modèles publics -- d'un autre agent.
Concrètement, CoordinatorAgent reçoit `state`, `plan`, `critique` en pur
duck-typing : il accède à leurs attributs (`plan.steps`, `step.step_id`,
`critique.status`...) sans jamais importer FarmState, Plan, PlanStep,
Critique ou CritiqueStatus depuis les modules des autres agents -- exactement
comme kaggriculture_agents/critic/agent.py accède à `plan.steps` sans importer
`kaggriculture_agents.planner.models.Plan`. Contrairement à kaggriculture_agents/critic/constants.py et
kaggriculture_agents/planner/constants.py, ce module n'a PAS besoin de dupliquer le
vocabulaire d'actions (WORKER_REQUIRED_ACTIONS...) : `PlanStep` porte déjà
la décision correspondante (`worker_required`), déjà prise par
PlannerAgent -- s'appuyer dessus plutôt que la redériver localement évite
tout risque de divergence (voir scheduler.py et README.md).
"""

# --- Statut requis pour coordonner un plan (spec section 5) ---------------
# Valeur de kaggriculture_agents/critic/models.CritiqueStatus.APPROVED -- comparée par
# VALEUR (critique.status.value), jamais en important l'enum elle-même
# (voir docstring du module).
APPROVED_STATUS_VALUE = "approved"

# --- Correspondance phase <-> tour de jeu (spec section 20) ---------------
# Simplification documentée et assumée : chaque phase d'un Plan (déjà
# construite par PlannerAgent en respectant dépendances et capacité workers,
# voir kaggriculture_agents/planner/agent.py._find_phase) est mappée sur EXACTEMENT un
# tour de jeu. Cohérent avec la façon dont EconomyAgent construit ses
# dépendances (une vente dépend d'une récolte antérieure ou du même tour de
# planification, jamais "plus tard dans le même tour").
TURNS_PER_PHASE = 1

# --- Raisons de blocage (évite les chaînes magiques dispersées) -----------
REASON_PLAN_NOT_APPROVED = "PLAN_NOT_APPROVED"
REASON_DEPENDENCY_CYCLE = "DEPENDENCY_CYCLE"
REASON_DEPENDENCY_ORDER_INVALID = "DEPENDENCY_ORDER_INVALID"
REASON_WORKER_UNAVAILABLE = "WORKER_UNAVAILABLE"
REASON_WORKER_CONFLICT = "WORKER_CONFLICT"
