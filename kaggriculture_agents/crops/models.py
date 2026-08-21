"""
Structures de données produites par le CropAgent.

CropProposal est une INTENTION, jamais une action exécutable directement :
elle sera consommée plus tard par PlannerAgent / CriticAgent /
CoordinatorAgent, qui décideront quoi en faire.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

Position = Tuple[int, int]


@dataclass(frozen=True)
class CropProposal:
    agent: str                      # toujours "crop" pour ce module
    action: str                     # "HARVEST" | "WATER" | "PLANT" | "FERTILIZE" | "DUG"
    target: Optional[Position]       # case concernée ; None pour BUY_SEED
    crop_type: Optional[str]        # type de culture concerné (None si non pertinent)
    priority: float                 # catégorie générale de l'action (0..1, voir constants.ACTION_PRIORITY)
    urgency: float                  # importance temporelle (0..1)
    expected_value: float           # valeur estimée en argent (heuristique, pas une garantie)
    score: float                    # qualité globale de la proposition (0..1, voir scoring.py)
    reason: str                     # explication lisible (pour audit / debug)
    confidence: float = 1.0         # confiance dans l'estimation (1.0 = donnée certaine)
    estimated_distance: Optional[float] = None
    quantity: float = 1.0  # distance au travailleur le plus proche (info, pas une affectation)
