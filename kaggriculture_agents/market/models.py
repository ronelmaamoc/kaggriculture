"""
Structures de données produites par le MarketAgent.

MarketProposal est une INTENTION, jamais une action exécutable directement :
elle sera consommée plus tard par EconomyAgent / PlannerAgent /
CoordinatorAgent, qui décideront quoi en faire (y compris la quantité
réellement vendue/achetée, qui appartient à une vision économique globale).

Structure volontairement symétrique à CropProposal / AnimalProposal
(kaggriculture_agents/crops/models.py, kaggriculture_agents/animals/models.py) pour que les futurs
agents (Coordinator, EconomyAgent...) puissent traiter les trois types de
proposition de façon homogène. Pas de champ `target` / distance ici : le
MarketAgent ne raisonne pas sur la position des travailleurs.

PriceAnalysis sépare explicitement "l'analyse du marché" (ce module) de
"la proposition d'action" (MarketProposal) — cette distinction est demandée
par la spec (section 36) car elle sera réutile telle quelle par les futurs
EconomyAgent / PlannerAgent, indépendamment de ce que le MarketAgent en a
lui-même proposé.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PriceAnalysis:
    product: str
    current_price: float
    base_price: Optional[float]     # None si produit inconnu de MARKET_PRODUCT_INFO
    normalized_price: float         # current_price / base_price ; 0.5 si base_price inconnu (documenté)
    price_level: str                # "LOW" | "NORMAL" | "HIGH"
    confidence: float               # 1.0 si base_price documenté, plus faible sinon
    demand_score: float = 0.0        # pression de demande observée/prévue (0..1)
    expected_price_factor: float = 1.0  # facteur de prix attendu à court terme
    ema_price: float = 0.0
    robust_slope: float = 0.0
    inventory_drift: float = 0.0
    projected_inventory_1d: float = 0.0
    projected_inventory_3d: float = 0.0
    projected_inventory_7d: float = 0.0
    forecast_price_1d: float = 0.0
    forecast_price_3d: float = 0.0
    forecast_price_7d: float = 0.0


@dataclass(frozen=True)
class MarketProposal:
    agent: str                      # toujours "market" pour ce module
    action: str                     # "SELL" | "HOLD" | "PRODUCE"
    product: str
    quantity: Optional[float]       # None si la proposition ne porte pas sur une quantité précise

    priority: float                 # catégorie générale de l'action (0..1, voir constants.ACTION_PRIORITY)
    urgency: float                  # importance temporelle (0..1)
    expected_value: float           # valeur brute estimée en argent (PAS un profit, voir scoring.py)

    score: float                    # qualité globale de la proposition (0..1, voir scoring.py)
    reason: str                     # explication lisible (pour audit / debug)
    confidence: float = 1.0         # confiance dans l'estimation (1.0 = donnée de marché certaine)