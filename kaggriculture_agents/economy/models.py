"""
Structures de données produites/consommées par l'EconomyAgent.

EconomyProposal est une INTENTION, jamais une action exécutable directement :
elle enveloppe UNE proposition source (CropProposal / AnimalProposal /
MarketProposal) avec une évaluation économique. Le PlannerAgent futur
choisira la combinaison finale ; l'EconomyAgent ne fait qu'évaluer chaque
opportunité indépendamment (spec section 6 et 31 : pas de construction du
plan complet ici).

BudgetAnalysis sépare "l'analyse budgétaire" (ce module) de l'évaluation des
propositions, réutilisable telle quelle par le futur PlannerAgent (spec
section 41, même logique que PriceAnalysis pour MarketAgent).
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class BudgetAnalysis:
    money: float
    reserve: float          # part de la trésorerie volontairement non engagée
    safe_budget: float      # money - reserve (jamais négatif)


@dataclass(frozen=True)
class EconomyProposal:
    agent: str                          # toujours "economy" pour ce module
    action: str                         # action de la proposition source (ex: "PLANT", "SELL", "HARVEST"...)
    source_agent: str                   # "crop" | "animal" | "market"
    target: Optional[object]            # position (crop/animal) ou None (market : pas de position)
    product: Optional[str]              # crop_type / animal_type / product selon la source

    cost: float                         # dépense immédiate estimée (0 si aucune, jamais inventée)
    expected_revenue: float             # revenu brut attendu (peut valoir 0, ex: HOLD)
    expected_profit: float              # expected_revenue - cost

    roi: Optional[float]                # expected_profit / cost ; None si cost <= 0 (pas de division par zéro)
    cash_delta: float                   # impact net sur la trésorerie si l'action est réalisée

    risk: float                         # 0..1, proportion du budget sécurisé engagée (+ pénalités documentées)
    urgency: float                      # reprise de l'urgence de la proposition source
    resource_efficiency: float          # profit par unité de coût/ressource engagée (voir scoring.py)

    economic_score: float               # qualité économique globale (0..1)

    reason: str                         # explication lisible (audit / debug)
    quantity: float = 1.0
    confidence: float = 1.0             # confiance héritée de la proposition source
    budget_constrained: bool = False    # True si cette proposition dépasse le budget sécurisé une fois les
                                         # propositions plus intéressantes déjà comptées (spec section 31-32)
    dependencies: Tuple[str, ...] = field(default_factory=tuple)
    bundle_id: Optional[str] = None
    bundle_role: Optional[str] = None
    synergy_bonus: float = 0.0
    bundle_net_value: float = 0.0
    # Références lisibles vers les propositions dont celle-ci dépend, ex:
    # ("crop:HARVEST:(4, 5)",) pour une vente qui suppose une récolte
    # préalable (évite le double comptage naïf, spec section 54-55).