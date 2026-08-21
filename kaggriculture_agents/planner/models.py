"""
Structures de données produites par le PlannerAgent.

Plan est le résultat final, jamais une action exécutable directement :
il enveloppe une séquence de PlanStep organisée en phases (actions
réalisables en parallèle par différents workers), respectant les
dépendances et les contraintes de ressources/budget/temps. L'exécution
réelle sera réalisée plus tard par un ExecutorAgent (hors scope ici).

PlanStep porte un `step_id` stable, dérivé de la proposition source
(`source_agent:action:target:product`), pour que `depends_on` puisse
référencer d'autres steps de façon lisible et pour l'audit / debug.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class PlanStep:
    step_id: str                    # ex: "crop:PLANT:(4, 5):WHEAT"
    action: str                     # action de la proposition source (HARVEST, WATER, PLANT, FEED, SELL...)
    source_agent: str                # "crop" | "animal" | "market"
    target: Optional[object]        # position (tuple) ou None (actions marché : pas de position)
    product: Optional[str]          # crop_type / animal_type / product selon la source

    phase: int                      # numéro de phase (0-indexé) ; les steps d'une même phase sont parallélisables

    priority: float                 # priorité de sélection retenue par le Planner (voir scoring.py)
    estimated_cost: float           # coût monétaire réel retenu (voir resources.py : distinction achat vs ressource déjà possédée)
    expected_revenue: float         # revenu brut attendu, hérité de EconomyProposal.expected_revenue
    expected_profit: float          # expected_revenue - estimated_cost, hérité de EconomyProposal.expected_profit

    worker_required: bool           # True si l'action nécessite qu'un worker soit physiquement sur la case
    worker_id: Optional[str]        # jamais renseigné dans cette version (voir README, "Ce que le Planner NE fait PAS")

    depends_on: Tuple[str, ...]     # step_id des steps dont celui-ci dépend (doivent être dans une phase antérieure)

    reason: str                     # explication lisible (audit / debug / mémoire)
    quantity: float = 1.0          # quantité pour les ordres marché
    confidence: float = 1.0         # confiance héritée de la proposition source


@dataclass(frozen=True)
class RejectedProposal:
    """
    Trace d'une proposition (économique) qui n'a PAS été retenue dans le
    plan final, avec la raison exacte. Conservée pour l'explicabilité
    (spec section 54) : un plan doit pouvoir justifier ce qu'il exclut,
    pas seulement ce qu'il inclut.
    """
    proposal_id: str                # même schéma d'identifiant que PlanStep.step_id
    action: str
    source_agent: str
    target: Optional[object]
    product: Optional[str]
    reason: str                     # ex: "budget sécurisé insuffisant", "doublon de crop:PLANT:(4,4):MELON"


@dataclass(frozen=True)
class Plan:
    steps: Tuple[PlanStep, ...] = field(default_factory=tuple)
    total_score: float = 0.0        # score global du plan (voir scoring.calculate_plan_score)
    total_cost: float = 0.0         # somme des estimated_cost des steps retenus
    expected_profit: float = 0.0    # valeur nette du plan (évite le double comptage HARVEST->SELL, voir scoring.py)
    confidence: float = 1.0         # confiance globale (voir scoring.calculate_plan_confidence)
    explanation: str = "Aucune proposition économique reçue."
    rejected: Tuple[RejectedProposal, ...] = field(default_factory=tuple)
    terminal_value: float = 0.0
    risk_budget: float = 0.0
    what_if_score: float = 0.0