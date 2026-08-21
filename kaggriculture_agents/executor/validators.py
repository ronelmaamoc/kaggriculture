"""
validators.py — Vérifications défensives avant d'envoyer une action à
l'environnement (spec sections 18, 20-21). Chaque agent en amont
(PlannerAgent, CriticAgent, CoordinatorAgent) a déjà validé le plan — ces
contrôles sont donc du même esprit "defense in depth" que
`kaggriculture_agents/coordinator/dependency_graph.py` : ils ne devraient normalement
rien trouver, mais protègent contre un état qui aurait changé entre la
construction du schedule et son exécution (spec section 22), ou contre une
incohérence résiduelle entre kaggriculture_agents.

Aucune fonction ici n'appelle l'environnement ni ne modifie `state`.
"""

from typing import Dict, Optional, Set, Tuple

from .constants import (
    CODE_INVALID_TARGET,
    CODE_WORKER_UNAVAILABLE,
    MARKET_SELL_ACTION,
    PLANT_ACTION,
)

Position = Tuple[int, int]


def build_crop_index(state) -> Dict[Position, object]:
    return {crop.position: crop for crop in state.crops.crops}


def build_animal_index(state) -> Dict[Position, object]:
    return {animal.position: animal for animal in state.animals.animals}


def check_worker_available(step, state, workers_used_this_turn: Set[str]) -> Optional[str]:
    """None si OK, sinon message d'erreur (CODE_WORKER_UNAVAILABLE)."""
    if step.worker_id is None:
        return None  # action marché : aucun worker requis
    known_ids = {w.worker_id for w in state.workers.all_workers}
    if step.worker_id not in known_ids:
        return f"Worker '{step.worker_id}' inconnu de FarmState (peut-être renvoyé chez lui depuis)."
    if step.worker_id in workers_used_this_turn:
        return f"Worker '{step.worker_id}' a déjà reçu une action ce tour (un seul par tour, README.md)."
    return None


def check_target_exists(step, state, crop_index: Dict[Position, object], animal_index: Dict[Position, object]) -> Optional[str]:
    """
    None si OK, sinon message d'erreur (CODE_INVALID_TARGET). PLANT et les
    actions marché n'ont pas de cible pré-existante à vérifier (PLANT vise
    une case VIDE par construction de CropAgent ; SELL ne porte pas de
    cible, voir kaggriculture_agents/market/models.py).
    """
    if step.action == MARKET_SELL_ACTION or step.action == PLANT_ACTION:
        return None
    if step.action in {"PICKUP", "DROP"}:
        # Shed is not a board tile. The target, when present, denotes one of
        # the four center access cells; the environment validates adjacency.
        return None
    if step.action in {"DUG", "DIG"}:
        weeds = set(getattr(getattr(state, "crops", None), "weed_tiles", ()))
        return None if step.target in weeds else f"Aucune mauvaise herbe à {step.target}."
    if step.action in {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "HIRE", "BUY_LAND"} or step.target is None:
        return None
    if step.action in {"BUILD_COOP", "BUILD_PASTURE"}:
        # Construction vise une case vide, pas un animal existant.
        if step.target in crop_index or step.target in animal_index:
            return f"La case {step.target} n'est pas libre pour {step.action}."
        return None
    if step.action == "PLACE":
        # PLACE consomme l'animal acheté présent dans le shed et cible une
        # structure vide : il n'existe donc volontairement aucun animal dans
        # animal_index à ce stade.
        return None

    if step.source_agent == "crop":
        crop = crop_index.get(step.target)
        if crop is None:
            return f"Aucune culture à {step.target} : elle a peut-être déjà été récoltée/retirée."
        if step.product and crop.crop_type != step.product:
            return f"La culture à {step.target} est '{crop.crop_type}', pas '{step.product}' comme prévu."
        return None

    if step.source_agent == "animal":
        animal = animal_index.get(step.target)
        if animal is None:
            return f"Aucun animal à {step.target} : il a peut-être fui ou déjà été retiré."
        if step.product and animal.animal_type != step.product:
            return f"L'animal à {step.target} est '{animal.animal_type}', pas '{step.product}' comme prévu."
        return None

    return None


def worker_position(step, state) -> Optional[Position]:
    for worker in state.workers.all_workers:
        if worker.worker_id == step.worker_id:
            return worker.position
    return None
