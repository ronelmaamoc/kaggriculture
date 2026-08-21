"""
action_mapper.py — Traduction ExecutionStep -> action Kaggriculture.

Ne contient AUCUNE règle de jeu (coûts, faisabilité...) : ça a déjà été
vérifié par CropAgent/AnimalAgent/MarketAgent/EconomyAgent/PlannerAgent/
CriticAgent en amont (spec section 14). Ce module fait uniquement de la
TRADUCTION de vocabulaire + la décision "faut-il d'abord se déplacer ?"
(spec section 13, contrainte réelle détaillée dans constants.py).
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from .constants import (
    CODE_INVALID_ACTION,
    CODE_UNSUPPORTED_ACTION,
    DEFAULT_SELL_QUANTITY,
    MARKET_SELL_ACTION,
    MOVE_EAST,
    MOVE_NORTH,
    MOVE_SOUTH,
    MOVE_WEST,
    PLANT_ACTION,
    SIMPLE_WORKER_ACTIONS,
    UNSUPPORTED_ACTIONS,
)


@dataclass(frozen=True)
class MappingOutcome:
    """Soit `action` est renseignée (succès), soit `error_code`/`error_message` le sont (échec)."""
    action: Optional[Tuple[str, ...]] = None
    is_move: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error_code is None


def move_towards(worker_position: Tuple[int, int], target: Tuple[int, int]) -> Tuple[str, ...]:
    """
    Un seul pas de déplacement vers `target` (jamais un chemin complet — un
    worker ne fait qu'une action par tour, voir constants.py). Priorité à
    l'axe X, déterministe.
    """
    dx = target[0] - worker_position[0]
    dy = target[1] - worker_position[1]
    if dx != 0:
        return (MOVE_EAST if dx > 0 else MOVE_WEST,)
    if dy != 0:
        return (MOVE_SOUTH if dy > 0 else MOVE_NORTH,)
    return ()  # déjà sur place (ne devrait pas être appelé dans ce cas)


def map_worker_action(step, worker_position: Tuple[int, int]) -> MappingOutcome:
    """
    Traduit un ExecutionStep destiné à un worker (farmer/hand) en action
    Kaggriculture. Si le worker n'est pas encore sur `step.target`, retourne
    un déplacement à la place de l'action prévue (spec section 22 —
    "utiliser l'état réel" ; ici, la position réelle du worker).
    """
    if step.action in UNSUPPORTED_ACTIONS:
        return MappingOutcome(
            error_code=CODE_UNSUPPORTED_ACTION,
            error_message=f"L'action analytique '{step.action}' n'est pas directement exécutable ; "
                           "elle doit être transformée en chaîne BUY_ANIMAL/BUILD_/PLACE en amont.",
        )

    if step.target is not None and worker_position != step.target:
        return MappingOutcome(action=move_towards(worker_position, step.target), is_move=True)

    if step.action == "DUG":
        # Internal strategy vocabulary uses DUG; Kaggriculture protocol uses DIG.
        return MappingOutcome(action=("DIG",))
    if step.action == PLANT_ACTION:
        return MappingOutcome(action=(PLANT_ACTION, step.product))
    if step.action in {"PLACE", "BUILD_COOP", "BUILD_PASTURE"}:
        if not step.product and step.action == "PLACE":
            return MappingOutcome(error_code=CODE_INVALID_ACTION, error_message="PLACE sans item.")
        if step.action == "PLACE":
            return MappingOutcome(action=("PLACE", step.product, max(1, int(round(getattr(step, "quantity", 1.0))))))
        return MappingOutcome(action=(step.action,))

    kaggriculture_action = SIMPLE_WORKER_ACTIONS.get(step.action)
    if kaggriculture_action is None:
        return MappingOutcome(
            error_code=CODE_INVALID_ACTION,
            error_message=f"Aucune action Kaggriculture connue pour '{step.action}'.",
        )
    return MappingOutcome(action=kaggriculture_action)


def map_market_order(step) -> MappingOutcome:
    """Traduit tous les ordres marché multi-agent vers le protocole Kaggriculture."""
    action = step.action
    qty = max(1, int(round(getattr(step, "quantity", 1.0))))
    if action == "SELL":
        if not step.product:
            return MappingOutcome(error_code=CODE_INVALID_ACTION, error_message="SELL sans produit.")
        return MappingOutcome(action=("SELL", step.product, qty))
    if action in {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL"}:
        if not step.product:
            return MappingOutcome(error_code=CODE_INVALID_ACTION, error_message=f"{action} sans produit.")
        return MappingOutcome(action=(action, step.product, qty))
    if action == "HIRE":
        return MappingOutcome(action=("HIRE",))
    if action == "BUY_LAND":
        return MappingOutcome(action=("BUY_LAND",))
    return MappingOutcome(error_code=CODE_INVALID_ACTION, error_message=f"'{action}' n'est pas un ordre marché exécutable.")
