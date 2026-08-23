"""InvestmentAgent — Amorçage et expansion avec réserve d'élevage (v7.2)."""

from typing import List
from ..animals.constants import ANIMAL_INFO
from ..crops.constants import CROP_INFO
from ..market.constants import MARKET_PRODUCT_INFO
from .models import InvestmentProposal

LAND_COSTS = (1000, 2000, 4000)


class InvestmentAgent:

    _STARTUP_HANDS = 4
    _MIDGAME_HANDS = 4

    @staticmethod
    def _fib(n: int) -> int:
        a, b = 1, 1
        if n <= 1:
            return 1
        for _ in range(2, n):
            a, b = b, a + b
        return b

    @classmethod
    def _hire_cost(cls, hire_number: int) -> float:
        return float(cls._fib(max(1, hire_number)))

    @staticmethod
    def _first_revenue_seen(state) -> bool:
        return (
            state.time.day >= 3
            or state.resources.money > 3000.0
            or any(
                int(state.resources.shed.get(k, 0)) > 0
                for k in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON")
            )
        )

    def decide(
        self,
        state,
        crop_proposals=(),
        animal_proposals=(),
        market_proposals=(),
    ) -> List[InvestmentProposal]:
        money = float(state.resources.money)
        proposals: List[InvestmentProposal] = []
        first_revenue = self._first_revenue_seen(state)
        current_hands = len(state.workers.hands)
        hires_today = int(state.player.hires_today)

        # 1. Main d'œuvre (4 ouvriers dès le début)
        target_hands = (
            self._MIDGAME_HANDS
            if first_revenue and state.time.day >= 3
            else self._STARTUP_HANDS
        )
        if current_hands < target_hands and state.time.day < 28:
            missing = target_hands - current_hands
            for offset in range(1, missing + 1):
                hire_number = hires_today + offset
                cost = self._hire_cost(hire_number)
                if money < cost:
                    break
                proposals.append(
                    InvestmentProposal(
                        action="HIRE",
                        product=f"HAND_{current_hands + offset}",
                        quantity=1,
                        cost=cost,
                        expected_profit=-cost,
                        urgency=0.99 if not first_revenue else 0.82,
                        score=0.99 if not first_revenue else 0.88,
                        reason="maintien de 4 hands",
                    )
                )
                money -= cost

        # 2. Expansion foncière : Calendrier sécurisé (J5, J10, J14)
        unlocked = len(state.land.unlocked_quadrants)
        thresholds = {1: 5, 2: 10, 3: 14}
        if unlocked < 4:
            required_day = thresholds.get(unlocked)
            expansion_horizon_ok = state.time.remaining_days >= 10
            if (
                required_day is not None
                and state.time.day >= required_day
                and expansion_horizon_ok
            ):
                cost = float(LAND_COSTS[min(unlocked - 1, len(LAND_COSTS) - 1)])
                reserve = max(350.0, money * 0.15)
                if money >= cost + reserve:
                    proposals.append(
                        InvestmentProposal(
                            action="BUY_LAND",
                            cost=cost,
                            expected_profit=0.0,
                            urgency=0.99,
                            score=0.98,
                            reason=f"achat quadrant #{unlocked + 1} à J{state.time.day}",
                        )
                    )
                    money -= cost

        # 3. Placement d'un animal acheté
        animal_has_place = any(
            getattr(p, "action", None) == "PLACE" for p in animal_proposals
        )
        if not animal_has_place:
            for animal, info in ANIMAL_INFO.items():
                if int(state.resources.shed.get(animal, 0)) <= 0:
                    continue
                for pos, kind in state.animals.empty_structures:
                    if kind != info["structure_kind"]:
                        continue
                    buy_id = f"animal:BUY_ANIMAL:None:{animal}"
                    proposals.append(
                        InvestmentProposal(
                            action="PLACE",
                            product=animal,
                            target=pos,
                            quantity=1,
                            cost=0.0,
                            expected_profit=info["max_held"]
                            * float(
                                state.market.prices.get(
                                    info["product"], info["base_price"]
                                )
                            ),
                            urgency=0.99,
                            score=0.99,
                            dependencies=(buy_id,),
                            reason=f"installation {animal}",
                        )
                    )
                    break

        # 4. Blé pour animaux
        animals = len(state.animals.animals)
        wheat = int(state.resources.shed.get("WHEAT", 0))
        if animals and wheat < max(4, animals * 2):
            qty = max(1, min(12, animals * 2 - wheat))
            price = float(state.market.prices.get("WHEAT", 25))
            cost = qty * price
            if money >= cost:
                proposals.append(
                    InvestmentProposal(
                        action="BUY_PRODUCT",
                        product="WHEAT",
                        quantity=qty,
                        cost=cost,
                        expected_profit=-cost,
                        urgency=1.0,
                        score=0.99,
                        reason="nourriture animale",
                    )
                )
                money -= cost

        return sorted(
            proposals,
            key=lambda p: (-p.urgency, -p.score, p.action, str(p.product)),
        )