"""
Structures de données produites par le PerceptionAgent.

Toutes les positions sont des tuples (x, y), cohérents avec le format
`farmer: [x, y]` de l'observation (x = colonne, y = ligne).

Ces classes ne contiennent AUCUNE logique de décision : elles décrivent
uniquement "ce qui est observé", jamais "ce qu'il faut faire".
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

Position = Tuple[int, int]


# --------------------------------------------------------------------------- #
# Temps
# --------------------------------------------------------------------------- #
@dataclass
class TimeState:
    step: int                      # obs["step"] — tour absolu (0-indexé)
    day: int                       # obs["day"]
    hour: int                      # obs["hour"] — tour dans la journée
    turns_per_day: int             # config (par défaut 24)
    episode_steps: int             # config (par défaut 720)
    remaining_turns: int
    remaining_days: int


# --------------------------------------------------------------------------- #
# Joueur / ressources privées
# --------------------------------------------------------------------------- #
@dataclass
class PlayerState:
    player_index: int              # obs["player"] (0 ou 1)
    money: float                   # obs["farms"][player_index]["money"]
    hires_today: int               # obs["farms"][player_index]["hires_today"]
    unlocked_quadrants: List[str]  # obs["farms"][player_index]["unlocked_quadrants"]


@dataclass
class ResourceState:
    money: float
    seeds: Dict[str, int]                  # obs["private"]["seeds"]
    shed: Dict[str, int]                   # obs["private"]["shed"]
    shed_used: int                         # somme des quantités du shed (hors graines)
    shed_capacity: int                     # config (par défaut 100)
    inventories: List[Dict[str, int]]      # obs["private"]["inventories"], [0]=farmer


# --------------------------------------------------------------------------- #
# Cultures
# --------------------------------------------------------------------------- #
@dataclass
class Crop:
    position: Position
    crop_type: str                         # WHEAT / CARROT / TOMATO / STRAWBERRY / MELON
    planted_day: int
    age_days: int                          # day - planted_day
    watered_today: bool
    consecutive_unwatered: int
    yield_units: int
    max_lifespan_step: int                 # -1 si culture "ongoing"
    fertilized_until_day: int              # -1 si jamais fertilisée
    is_fertilized_now: bool                # fertilized_until_day >= day courant
    ready_to_harvest: bool                 # yield_units > 0
    needs_water: bool                      # not watered_today
    at_risk: bool                          # consecutive_unwatered >= seuil de risque


@dataclass
class CropState:
    crops: List[Crop] = field(default_factory=list)
    ready_to_harvest: List[Crop] = field(default_factory=list)
    need_water: List[Crop] = field(default_factory=list)
    at_risk: List[Crop] = field(default_factory=list)
    empty_tiles: List[Position] = field(default_factory=list)
    weed_tiles: List[Position] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Animaux
# --------------------------------------------------------------------------- #
@dataclass
class Animal:
    position: Position
    structure_kind: str                    # COOP ou PASTURE
    animal_type: str                        # GOOSE / COW / SHEEP
    placed_day: int
    yield_units: int
    fed_today: bool
    consecutive_unfed: int
    cared_today: bool
    fertilizer_available: bool
    pending_care_bonus: int
    needs_feed: bool                        # not fed_today
    needs_care: bool                        # not cared_today
    at_risk: bool                           # consecutive_unfed >= seuil de risque
    ready_to_harvest: bool                  # yield_units > 0


@dataclass
class AnimalState:
    animals: List[Animal] = field(default_factory=list)
    need_feed: List[Animal] = field(default_factory=list)
    need_care: List[Animal] = field(default_factory=list)
    at_risk: List[Animal] = field(default_factory=list)
    ready_to_harvest: List[Animal] = field(default_factory=list)
    empty_structures: List[Tuple[Position, str]] = field(default_factory=list)  # (pos, kind) sans animal


# --------------------------------------------------------------------------- #
# Travailleurs
# --------------------------------------------------------------------------- #
@dataclass
class Worker:
    worker_id: str          # "farmer" ou "hand_0", "hand_1", ...
    role: str                # "farmer" ou "hand"
    position: Position


@dataclass
class WorkerState:
    farmer: Optional[Worker]
    hands: List[Worker] = field(default_factory=list)

    @property
    def all_workers(self) -> List[Worker]:
        return ([self.farmer] if self.farmer else []) + self.hands


# --------------------------------------------------------------------------- #
# Terrain
# --------------------------------------------------------------------------- #
@dataclass
class LandState:
    unlocked_quadrants: List[str]
    locked_quadrants: List[str]
    board_size: int
    locked_tiles: List[Position] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Marché
# --------------------------------------------------------------------------- #
@dataclass
class MarketState:
    prices: Dict[str, int]
    inventory: Dict[str, int]
    buyable_products: List[str]   # constantes du jeu (WHEAT, FERTILIZER)


# --------------------------------------------------------------------------- #
# Ville
# --------------------------------------------------------------------------- #
@dataclass
class TownState:
    unlocked_shops: List[str]
    shop_counts: Dict[str, int]   # agrégation simple de unlocked_shops


# --------------------------------------------------------------------------- #
# Adversaire (état public uniquement — le shed adverse est invisible)
# --------------------------------------------------------------------------- #
@dataclass
class OpponentState:
    player_index: int
    money: float
    unlocked_quadrants: List[str]
    farmer_position: Position
    hands_positions: List[Position]
    planted_crop_count: int
    animal_count: int


# --------------------------------------------------------------------------- #
# Risques
# --------------------------------------------------------------------------- #
@dataclass
class RiskState:
    crops_at_risk: List[Crop] = field(default_factory=list)
    animals_at_risk: List[Animal] = field(default_factory=list)
    weed_count: int = 0
    shed_near_capacity: bool = False
    resource_shortages: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# État global
# --------------------------------------------------------------------------- #
@dataclass
class FarmState:
    time: TimeState
    player: PlayerState
    resources: ResourceState
    crops: CropState
    animals: AnimalState
    workers: WorkerState
    land: LandState
    market: MarketState
    town: TownState
    opponent: OpponentState
    risks: RiskState
