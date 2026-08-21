"""
agent.py — PerceptionAgent, le point d'entrée public du module.

API publique :

    perception = PerceptionAgent()
    state = perception.analyze(obs)   # -> FarmState

PerceptionAgent n'observe et n'analyse QUE l'état courant. Il ne produit
jamais d'action Kaggriculture (PLANT, WATER, HARVEST, FEED, SELL, BUY, HIRE,
BUY_LAND, ...) et ne contient aucune stratégie de décision.
"""

from typing import Any, Dict

from . import analyzers, parsers
from .constants import (
    DEFAULT_EPISODE_STEPS,
    DEFAULT_SHED_CAPACITY,
    DEFAULT_TURNS_PER_DAY,
)
from .models import FarmState


class PerceptionError(Exception):
    """Levée quand `obs` est structurellement invalide (pas juste incomplet)."""


class PerceptionAgent:
    """
    Transforme l'observation brute de Kaggriculture en un `FarmState`
    structuré, exploitable par les futurs agents de décision (CropAgent,
    AnimalAgent, MarketAgent, ...).

    Les paramètres episode_steps / turns_per_day / shed_capacity ne sont PAS
    disponibles dans `obs` (ce sont des paramètres de configuration
    d'épisode). Ils valent par défaut les valeurs par défaut documentées dans
    README.md ; si la partie a été créée avec une configuration différente,
    passe-les explicitement.
    """

    def __init__(
        self,
        episode_steps: int = DEFAULT_EPISODE_STEPS,
        turns_per_day: int = DEFAULT_TURNS_PER_DAY,
        shed_capacity: int = DEFAULT_SHED_CAPACITY,
    ) -> None:
        self.episode_steps = episode_steps
        self.turns_per_day = turns_per_day
        self.shed_capacity = shed_capacity

    def analyze(self, obs: Dict[str, Any]) -> FarmState:
        self._validate(obs)

        raw_time = parsers.parse_time(obs)
        raw_player = parsers.parse_player(obs)
        raw_resources = parsers.parse_resources(obs)
        raw_tiles = parsers.parse_tiles(obs)
        raw_workers = parsers.parse_workers(obs)
        raw_market = parsers.parse_market(obs)
        raw_town = parsers.parse_town(obs)
        raw_opponent = parsers.parse_opponent(obs)

        time_state = analyzers.analyze_time(raw_time, self.episode_steps, self.turns_per_day)
        player_state = analyzers.analyze_player(raw_player)
        resource_state = analyzers.analyze_resources(raw_resources, self.shed_capacity)
        crop_state = analyzers.analyze_crops(raw_tiles, current_day=raw_time["day"])
        animal_state = analyzers.analyze_animals(raw_tiles)
        worker_state = analyzers.analyze_workers(raw_workers)
        land_state = analyzers.analyze_land(raw_player, raw_tiles)
        market_state = analyzers.analyze_market(raw_market)
        town_state = analyzers.analyze_town(raw_town)
        opponent_state = analyzers.analyze_opponent(raw_opponent)
        risk_state = analyzers.detect_risks(crop_state, animal_state, resource_state)

        return FarmState(
            time=time_state,
            player=player_state,
            resources=resource_state,
            crops=crop_state,
            animals=animal_state,
            workers=worker_state,
            land=land_state,
            market=market_state,
            town=town_state,
            opponent=opponent_state,
            risks=risk_state,
        )

    @staticmethod
    def _validate(obs: Dict[str, Any]) -> None:
        """
        Vérifie que les clés structurellement indispensables sont présentes.
        Une observation "partielle" (ex: town vide) est acceptée ; une
        observation qui n'a pas la forme d'une obs Kaggriculture ne l'est pas.
        """
        if not isinstance(obs, dict):
            raise PerceptionError(f"obs doit être un dict, reçu {type(obs)!r}")

        if "farms" not in obs:
            raise PerceptionError("obs invalide : clé 'farms' absente")

        player = obs.get("player", 0)
        farms = obs["farms"]
        if not isinstance(farms, list) or player >= len(farms):
            raise PerceptionError(
                f"obs invalide : 'farms' ne contient pas d'entrée pour player={player}"
            )
