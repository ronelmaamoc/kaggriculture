"""
Structures de données produites par l'AnimalAgent.

AnimalProposal est une INTENTION, jamais une action exécutable directement :
elle sera consommée plus tard par PlannerAgent / CriticAgent /
CoordinatorAgent, qui décideront quoi en faire (y compris l'affectation
Farmer / Hand, qui n'appartient PAS à cet agent).

Structure volontairement symétrique à CropProposal (kaggriculture_agents/crops/models.py)
pour que les futurs agents (Coordinator, TaskAllocator...) puissent traiter
les deux types de proposition de façon homogène.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

Position = Tuple[int, int]


@dataclass(frozen=True)
class AnimalProposal:
    agent: str                      # toujours "animal" pour ce module
    action: str                     # "FEED" | "CARE" | "HARVEST" | "COLLECT_FERTILIZER" | "PICKUP" | "PLACE" | "EXPANSION_OPPORTUNITY"
    target: Optional[Position]       # case concernée ; None pour BUY_ANIMAL
    animal_type: Optional[str]      # GOOSE / COW / SHEEP ; None si structure vide sans candidat unique
    priority: float                 # catégorie générale de l'action (0..1, voir constants.ACTION_PRIORITY)
    urgency: float                  # importance temporelle (0..1)
    expected_value: float           # valeur estimée en argent (heuristique, pas une garantie)
    score: float                    # qualité globale de la proposition (0..1, voir scoring.py)
    reason: str                     # explication lisible (pour audit / debug)
    confidence: float = 1.0         # confiance dans l'estimation (1.0 = donnée certaine)
    estimated_distance: Optional[float] = None
    quantity: float = 1.0  # distance au travailleur le plus proche (info, pas une affectation)