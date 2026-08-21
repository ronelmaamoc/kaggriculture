"""
rules.py — Règles de faisabilité STATIQUE pour le PlannerAgent.

Une proposition "impossible" (spec section 8-9) est rejetée ici, AVANT
toute sélection : ce sont des vérifications qui ne dépendent PAS des
autres propositions retenues (pour ça, voir resources.py / agent.py, qui
gèrent le budget et les ressources partagées au fur et à mesure de la
construction du plan).

Important (documenté, spec section 9) : une proposition simplement "peu
intéressante" (faible `economic_score`) N'EST PAS filtrée ici. Elle reste
candidate et sera naturellement écartée par l'ordonnancement glouton
(scoring.selection_key) si les ressources manquent -- filtrer sur un score
faible confondrait "impossible" et "peu prioritaire", ce que la spec
interdit explicitement.
"""

from typing import Optional

from .constants import CASH_CONSUMING_ACTIONS, NON_ACTIONABLE_ACTIONS, RESOURCE_CONSUMPTION


def is_actionable(action: str) -> bool:
    """HOLD est une recommandation ("ne rien faire"), pas une action Kaggriculture exécutable."""
    return action not in NON_ACTIONABLE_ACTIONS


def has_valid_target(ep) -> bool:
    """
    Les actions marché (SELL/HOLD/PRODUCE) n'ont jamais de target
    (MarketProposal ne porte pas de position, voir kaggriculture_agents/market/models.py)
    : c'est attendu, pas une erreur. Les actions crop/animal doivent en
    revanche en avoir une -- défensif, ne devrait jamais échouer si
    CropAgent/AnimalAgent respectent leur propre contrat.
    """
    if ep.source_agent == "market":
        return True
    if ep.source_agent == "crop" and ep.action == "BUY_SEED":
        return True
    if ep.source_agent == "animal" and ep.action == "BUY_ANIMAL":
        return True
    if ep.source_agent == "investment" and ep.action in {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "HIRE", "BUY_LAND"}:
        return True
    return ep.target is not None


def is_absolutely_affordable(cost: float, total_money: float) -> bool:
    """
    Vérifie une impossibilité ABSOLUE (spec section 8 : "coût > argent
    disponible"), sans réserve de sécurité (ça, c'est le rôle de
    resources.BudgetLedger une fois la sélection en cours -- ici on
    élimine seulement ce qui ne sera jamais finançable, quel que soit
    l'ordre du plan).
    """
    return cost <= total_money


def is_resource_known_available(ep, state, planned_proposals=()) -> bool:
    """
    Vérifie qu'au moins 1 unité de la ressource nommée consommée par cette
    action existe actuellement dans FarmState. Défensif : CropAgent /
    AnimalAgent ne proposent normalement déjà que des actions dont la
    ressource est disponible (voir rules.can_be_planted / can_be_fertilized
    / feed_available dans leurs modules respectifs) -- ce filtre protège
    contre une incohérence amont plutôt que de la masquer silencieusement.
    """
    getter = RESOURCE_CONSUMPTION.get((ep.source_agent, ep.action))
    if getter is None:
        return True
    key = getter(ep)
    if key.startswith("SEED_"):
        available = state.resources.seeds.get(key[len("SEED_"):], 0)
    elif key.startswith("ANIMAL_"):
        available = state.resources.shed.get(key[len("ANIMAL_"):], 0)
    else:
        available = state.resources.shed.get(key, 0)
    if available > 0:
        return True

    # A resource may be produced/acquired by another proposal in the SAME
    # candidate portfolio.  The ResourceLedger already models these
    # transitions (BUY_SEED/BUY_PRODUCT/BUY_ANIMAL, HARVEST,
    # COLLECT_FERTILIZER), so rejecting here would incorrectly discard valid
    # chains such as COLLECT_FERTILIZER -> FERTILIZE or BUY_SEED -> PLANT.
    for other in planned_proposals:
        action = getattr(other, "action", None)
        product = getattr(other, "product", None)
        source = getattr(other, "source_agent", None)
        if key.startswith("SEED_") and action == "BUY_SEED" and product == key[5:]:
            return True
        if key.startswith("ANIMAL_") and action == "BUY_ANIMAL" and product == key[7:]:
            return True
        # PICKUP -> PLACE is a two-step resource transition. FarmState does
        # not expose worker inventory before execution, so a matching PICKUP
        # in the same portfolio can legitimately create INVENTORY_* later.
        if key.startswith("INVENTORY_") and action == "PICKUP" and product == key[10:]:
            return True
        if key == "FERTILIZER" and action == "COLLECT_FERTILIZER":
            return True
        if key == "WHEAT" and action == "HARVEST" and source == "crop" and product == "WHEAT":
            return True
        if action == "BUY_PRODUCT" and product == key:
            return True
    return False


def is_feasible(ep, state, planned_proposals=()) -> Optional[str]:
    """
    Point d'entrée unique de la faisabilité statique. Retourne `None` si
    faisable, sinon une chaîne expliquant pourquoi elle est rejetée
    (utilisée telle quelle comme `RejectedProposal.reason`).
    """
    if not is_actionable(ep.action):
        return "action informationnelle (HOLD) : aucune action Kaggriculture à planifier"
    if not has_valid_target(ep):
        return "aucune cible valide (incohérence amont, defensive check)"
    if ep.action in CASH_CONSUMING_ACTIONS and not is_absolutely_affordable(ep.cost, state.resources.money):
        return f"coût ({ep.cost:.0f}$) supérieur à la trésorerie totale disponible ({state.resources.money:.0f}$)"
    if not is_resource_known_available(ep, state, planned_proposals):
        return "ressource nommée requise indisponible dans FarmState (incohérence amont, defensive check)"
    return None