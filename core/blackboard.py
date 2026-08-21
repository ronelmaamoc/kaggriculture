"""
core/blackboard.py — Mémoire partagée d'UN tour de décision (spec section 5).

Portée volontairement limitée à un seul tour (spec section 9, "ne pas
conserver d'hypothèses obsolètes sur la ferme entre deux tours") : `main.py`
crée un `Blackboard` neuf à chaque appel de `agent(obs)`, jamais réutilisé
d'un tour à l'autre. La mémoire qui DOIT survivre entre deux tours (par
exemple l'idempotence de `ExecutorAgent`, `self._completed_batches`) reste
interne aux instances d'agents elles-mêmes, créées une seule fois par
`main.py` — le Blackboard ne s'en occupe pas (spec section 9, séparation
explicite "snapshot courant" vs "mémoire persistante d'agent").

API strictement lecture/écriture explicite (spec section 5, "pas un
dictionnaire global totalement libre") : chaque étape du pipeline a un
getter/setter dédié, jamais `blackboard.anything = anything`.
"""

from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple


@dataclass
class Blackboard:
    _state: Optional[object] = field(default=None, repr=False)
    _crop_proposals: Tuple = field(default=(), repr=False)
    _animal_proposals: Tuple = field(default=(), repr=False)
    _market_proposals: Tuple = field(default=(), repr=False)
    _investment_proposals: Tuple = field(default=(), repr=False)
    _economy_proposals: Tuple = field(default=(), repr=False)
    _plan: Optional[object] = field(default=None, repr=False)
    _critique: Optional[object] = field(default=None, repr=False)
    _schedule: Optional[object] = field(default=None, repr=False)
    _result: Optional[object] = field(default=None, repr=False)

    # --- FarmState ------------------------------------------------------
    def set_state(self, state) -> None:
        self._state = state

    def get_state(self):
        return self._state

    # --- CropAgent --------------------------------------------------------
    def set_crop_analysis(self, proposals: Sequence) -> None:
        self._crop_proposals = tuple(proposals)

    def get_crop_analysis(self) -> Tuple:
        return self._crop_proposals

    # --- AnimalAgent ------------------------------------------------------
    def set_animal_analysis(self, proposals: Sequence) -> None:
        self._animal_proposals = tuple(proposals)

    def get_animal_analysis(self) -> Tuple:
        return self._animal_proposals

    # --- MarketAgent ------------------------------------------------------
    def set_market_analysis(self, proposals: Sequence) -> None:
        self._market_proposals = tuple(proposals)

    def get_market_analysis(self) -> Tuple:
        return self._market_proposals

    # --- EconomyAgent -----------------------------------------------------
    def set_investment_analysis(self, proposals: Sequence) -> None:
        self._investment_proposals = tuple(proposals)

    def get_investment_analysis(self) -> Tuple:
        return self._investment_proposals

    # --- EconomyAgent -----------------------------------------------------
    def set_economic_analysis(self, proposals: Sequence) -> None:
        self._economy_proposals = tuple(proposals)

    def get_economic_analysis(self) -> Tuple:
        return self._economy_proposals

    # --- PlannerAgent -----------------------------------------------------
    def set_plan(self, plan) -> None:
        self._plan = plan

    def get_plan(self):
        return self._plan

    # --- CriticAgent ------------------------------------------------------
    def set_critique(self, critique) -> None:
        self._critique = critique

    def get_critique(self):
        return self._critique

    # --- CoordinatorAgent ---------------------------------------------------
    def set_execution_schedule(self, schedule) -> None:
        self._schedule = schedule

    def get_execution_schedule(self):
        return self._schedule

    # --- ExecutorAgent ------------------------------------------------------
    def set_execution_result(self, result) -> None:
        self._result = result

    def get_execution_result(self):
        return self._result

    # --- Traçabilité --------------------------------------------------------
    def snapshot(self) -> dict:
        """Vue d'ensemble en lecture seule, pour le logging/débogage (jamais utilisée pour piloter la logique métier)."""
        return {
            "state": self._state,
            "crop_proposals": self._crop_proposals,
            "animal_proposals": self._animal_proposals,
            "market_proposals": self._market_proposals,
            "investment_proposals": self._investment_proposals,
            "economy_proposals": self._economy_proposals,
            "plan": self._plan,
            "critique": self._critique,
            "schedule": self._schedule,
            "result": self._result,
        }
