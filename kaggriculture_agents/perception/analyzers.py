"""
analyzers.py — Dérive des informations d'ANALYSE à partir des données brutes
extraites par parsers.py.

Règle absolue : un analyzer peut catégoriser, calculer un âge, détecter un
risque... mais ne doit JAMAIS produire d'action de jeu (WATER, FEED, SELL...).
Il décrit un état ("cette culture est à risque"), il ne prescrit rien
("il faut arroser cette culture").
"""

from typing import Any, Dict, List, Tuple

from .constants import (
    ANIMAL_STRUCTURE_KINDS,
    MARKET_BUYABLE_PRODUCTS,
    RISK_CONSECUTIVE_THRESHOLD,
)
from .models import (
    Animal,
    AnimalState,
    Crop,
    CropState,
    LandState,
    MarketState,
    OpponentState,
    PlayerState,
    ResourceState,
    RiskState,
    TimeState,
    TownState,
    Worker,
    WorkerState,
)

Position = Tuple[int, int]


# --------------------------------------------------------------------------- #
# Temps
# --------------------------------------------------------------------------- #
def calculate_remaining_turns(step: int, episode_steps: int) -> int:
    return max(episode_steps - step, 0)


def calculate_remaining_days(day: int, episode_steps: int, turns_per_day: int) -> int:
    total_days = episode_steps // turns_per_day
    return max(total_days - day, 0)


def analyze_time(raw_time: Dict[str, int], episode_steps: int, turns_per_day: int) -> TimeState:
    step, day, hour = raw_time["step"], raw_time["day"], raw_time["hour"]
    return TimeState(
        step=step,
        day=day,
        hour=hour,
        turns_per_day=turns_per_day,
        episode_steps=episode_steps,
        remaining_turns=calculate_remaining_turns(step, episode_steps),
        remaining_days=calculate_remaining_days(day, episode_steps, turns_per_day),
    )


# --------------------------------------------------------------------------- #
# Joueur / ressources
# --------------------------------------------------------------------------- #
def analyze_player(raw_player: Dict[str, Any]) -> PlayerState:
    return PlayerState(
        player_index=raw_player["player_index"],
        money=raw_player["money"],
        hires_today=raw_player["hires_today"],
        unlocked_quadrants=raw_player["unlocked_quadrants"],
    )


def analyze_resources(raw_resources: Dict[str, Any], shed_capacity: int) -> ResourceState:
    shed = raw_resources["shed"]
    shed_used = sum(v for v in shed.values() if isinstance(v, (int, float)))
    return ResourceState(
        money=raw_resources["money"],
        seeds=raw_resources["seeds"],
        shed=shed,
        shed_used=shed_used,
        shed_capacity=shed_capacity,
        inventories=raw_resources["inventories"],
    )


# --------------------------------------------------------------------------- #
# Cultures
# --------------------------------------------------------------------------- #
def _build_crop(position: Position, tile: Dict[str, Any], current_day: int) -> Crop:
    planted_day = tile.get("planted_day", current_day)
    fertilized_until_day = tile.get("fertilized_until_day", -1)
    consecutive_unwatered = tile.get("consecutive_unwatered", 0)
    yield_units = tile.get("yield_units", 0)
    watered_today = tile.get("watered_today", False)

    return Crop(
        position=position,
        crop_type=tile.get("crop"),
        planted_day=planted_day,
        age_days=current_day - planted_day,
        watered_today=watered_today,
        consecutive_unwatered=consecutive_unwatered,
        yield_units=yield_units,
        max_lifespan_step=tile.get("max_lifespan_step", -1),
        fertilized_until_day=fertilized_until_day,
        is_fertilized_now=fertilized_until_day >= current_day,
        ready_to_harvest=yield_units > 0,
        needs_water=not watered_today,
        at_risk=consecutive_unwatered >= RISK_CONSECUTIVE_THRESHOLD,
    )


def detect_ready_crops(crops: List[Crop]) -> List[Crop]:
    return [c for c in crops if c.ready_to_harvest]


def detect_crops_needing_water(crops: List[Crop]) -> List[Crop]:
    return [c for c in crops if c.needs_water]


def detect_crops_at_risk(crops: List[Crop]) -> List[Crop]:
    return [c for c in crops if c.at_risk]


def analyze_crops(raw_tiles: Dict[str, Any], current_day: int) -> CropState:
    crops = [_build_crop(pos, tile, current_day) for pos, tile in raw_tiles["plant_tiles"]]
    return CropState(
        crops=crops,
        ready_to_harvest=detect_ready_crops(crops),
        need_water=detect_crops_needing_water(crops),
        at_risk=detect_crops_at_risk(crops),
        empty_tiles=raw_tiles["empty_tiles"],
        weed_tiles=raw_tiles["weed_tiles"],
    )


# --------------------------------------------------------------------------- #
# Animaux
# --------------------------------------------------------------------------- #
def _build_animal(position: Position, structure: Dict[str, Any]) -> Animal:
    consecutive_unfed = structure.get("consecutive_unfed", 0)
    fed_today = structure.get("fed_today", False)
    cared_today = structure.get("cared_today", False)
    yield_units = structure.get("yield_units", 0)

    return Animal(
        position=position,
        structure_kind=structure.get("kind"),
        animal_type=structure.get("animal"),
        placed_day=structure.get("placed_day", 0),
        yield_units=yield_units,
        fed_today=fed_today,
        consecutive_unfed=consecutive_unfed,
        cared_today=cared_today,
        fertilizer_available=structure.get("fertilizer_available", False),
        pending_care_bonus=structure.get("pending_care_bonus", 0),
        needs_feed=not fed_today,
        needs_care=not cared_today,
        at_risk=consecutive_unfed >= RISK_CONSECUTIVE_THRESHOLD,
        ready_to_harvest=yield_units > 0,
    )


def detect_animals_at_risk(animals: List[Animal]) -> List[Animal]:
    return [a for a in animals if a.at_risk]


def analyze_animals(raw_tiles: Dict[str, Any]) -> AnimalState:
    animals: List[Animal] = []
    empty_structures: List[Tuple[Position, str]] = []

    for pos, structure in raw_tiles["structure_tiles"]:
        if structure.get("animal"):
            animals.append(_build_animal(pos, structure))
        else:
            empty_structures.append((pos, structure.get("kind")))

    return AnimalState(
        animals=animals,
        need_feed=[a for a in animals if a.needs_feed],
        need_care=[a for a in animals if a.needs_care],
        at_risk=detect_animals_at_risk(animals),
        ready_to_harvest=[a for a in animals if a.ready_to_harvest],
        empty_structures=empty_structures,
    )


# --------------------------------------------------------------------------- #
# Travailleurs
# --------------------------------------------------------------------------- #
def analyze_workers(raw_workers: Dict[str, Any]) -> WorkerState:
    farmer = None
    if raw_workers["farmer_position"] is not None:
        farmer = Worker(worker_id="farmer", role="farmer", position=raw_workers["farmer_position"])

    hands = [
        Worker(worker_id=f"hand_{i}", role="hand", position=pos)
        for i, pos in enumerate(raw_workers["hands_positions"])
    ]

    return WorkerState(farmer=farmer, hands=hands)


# --------------------------------------------------------------------------- #
# Terrain
# --------------------------------------------------------------------------- #
def analyze_land(raw_player: Dict[str, Any], raw_tiles: Dict[str, Any]) -> LandState:
    unlocked = raw_player["unlocked_quadrants"]
    locked = [q for q in ("NW", "NE", "SW", "SE") if q not in unlocked]
    return LandState(
        unlocked_quadrants=unlocked,
        locked_quadrants=locked,
        board_size=raw_tiles["board_size"],
        locked_tiles=raw_tiles["locked_tiles"],
    )


# --------------------------------------------------------------------------- #
# Marché / ville
# --------------------------------------------------------------------------- #
def analyze_market(raw_market: Dict[str, Any]) -> MarketState:
    return MarketState(
        prices=raw_market["prices"],
        inventory=raw_market["inventory"],
        buyable_products=list(MARKET_BUYABLE_PRODUCTS),
    )


def analyze_town(raw_town: Dict[str, Any]) -> TownState:
    shops = raw_town["unlocked_shops"]
    counts: Dict[str, int] = {}
    for shop in shops:
        counts[shop] = counts.get(shop, 0) + 1
    return TownState(unlocked_shops=shops, shop_counts=counts)


# --------------------------------------------------------------------------- #
# Adversaire
# --------------------------------------------------------------------------- #
def analyze_opponent(raw_opponent: Dict[str, Any]) -> OpponentState:
    tiles = raw_opponent.get("tiles", [])
    planted = 0
    animal_count = 0
    for row in tiles:
        for tile in row:
            if isinstance(tile, dict):
                if tile.get("kind") == "PLANT":
                    planted += 1
                elif tile.get("kind") in ANIMAL_STRUCTURE_KINDS and tile.get("animal"):
                    animal_count += 1

    return OpponentState(
        player_index=raw_opponent["player_index"],
        money=raw_opponent["money"],
        unlocked_quadrants=raw_opponent["unlocked_quadrants"],
        farmer_position=raw_opponent["farmer_position"],
        hands_positions=raw_opponent["hands_positions"],
        planted_crop_count=planted,
        animal_count=animal_count,
    )


# --------------------------------------------------------------------------- #
# Risques
# --------------------------------------------------------------------------- #
def detect_resource_shortages(resources: ResourceState) -> List[str]:
    """
    Signale, de façon purement descriptive, les ressources privées à zéro.
    Ne décide d'aucun achat — juste un constat factuel.
    """
    shortages = []
    if resources.money <= 0:
        shortages.append("money")
    if not resources.seeds or all(v <= 0 for v in resources.seeds.values()):
        shortages.append("seeds")
    return shortages


def detect_risks(
    crop_state: CropState,
    animal_state: AnimalState,
    resource_state: ResourceState,
) -> RiskState:
    shed_near_capacity = (
        resource_state.shed_capacity > 0
        and resource_state.shed_used >= 0.9 * resource_state.shed_capacity
    )
    return RiskState(
        crops_at_risk=crop_state.at_risk,
        animals_at_risk=animal_state.at_risk,
        weed_count=len(crop_state.weed_tiles),
        shed_near_capacity=shed_near_capacity,
        resource_shortages=detect_resource_shortages(resource_state),
    )