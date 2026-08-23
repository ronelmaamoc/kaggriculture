"""MarketAgent — Marché dynamique et ventes alignées avec main.py (v7.2)."""

from collections import deque
from dataclasses import replace
import math
from typing import Dict, List

from .analyzers import (
    analyze_prices,
    find_hold_opportunities,
    find_production_opportunities,
    find_sell_opportunities,
)
from .constants import MARKET_CURVE_PARAMS, MARKET_PRODUCT_INFO
from .demand import build_demand_forecast
from .models import MarketProposal, PriceAnalysis


class MarketAgent:

    def __init__(self, history_size: int = 12) -> None:
        self._history: Dict[str, deque] = {}
        self._inventory_history: Dict[str, deque] = {}
        self._ema: Dict[str, float] = {}
        self._last_inventory: Dict[str, float] = {}
        self._pending_market_flow: Dict[str, float] = {}
        self._history_size = history_size

    def reset(self) -> None:
        self._history.clear()
        self._inventory_history.clear()
        self._ema.clear()
        self._last_inventory.clear()
        self._pending_market_flow.clear()

    def _record_prices(self, state) -> None:
        for product, price in state.market.prices.items():
            q = self._history.setdefault(
                product, deque(maxlen=self._history_size)
            )
            if not q or q[-1] != price:
                q.append(float(price))
            previous_ema = self._ema.get(product, float(price))
            self._ema[product] = 0.80 * previous_ema + 0.20 * float(price)

            inv = float(state.market.inventory.get(product, 10000.0))
            iq = self._inventory_history.setdefault(
                product, deque(maxlen=self._history_size)
            )
            if not iq or iq[-1] != inv:
                iq.append(inv)

    def decide(self, state) -> List[MarketProposal]:
        self._record_prices(state)
        price_analyses = analyze_prices(state)
        proposals: List[MarketProposal] = []
        proposals += find_sell_opportunities(state, price_analyses)
        proposals += find_hold_opportunities(state, price_analyses)
        proposals += find_production_opportunities(state, price_analyses)
        proposals = self._dynamic_sales(state, proposals, price_analyses)
        return sorted(
            proposals,
            key=lambda p: (-p.score, -p.urgency, p.action, p.product),
        )

    def _dynamic_sales(
        self,
        state,
        proposals: List[MarketProposal],
        analyses: List[PriceAnalysis],
    ) -> List[MarketProposal]:
        result = [p for p in proposals if p.action not in ("SELL", "HOLD")]
        total_shed_used = sum(
            int(v)
            for k, v in state.resources.shed.items()
            if isinstance(v, (int, float))
        )

        for product, quantity in state.resources.shed.items():
            qty = int(quantity)
            if qty <= 0 or product not in state.market.prices:
                continue

            if product == "FERTILIZER" and qty <= 2:
                continue
            if (
                product == "WHEAT"
                and len(state.animals.animals) > 0
                and qty <= len(state.animals.animals) * 2
            ):
                continue

            info = MARKET_PRODUCT_INFO.get(product)
            if not info:
                continue

            price = float(state.market.prices[product])
            base = float(info["base_price"])
            norm = price / max(1.0, base)

            # Dans la fenêtre du soir (18h-23h), vendre la totalité du stock disponible
            if state.time.remaining_days <= 1 or total_shed_used >= 70:
                sell_qty = qty
                urgency = 0.95
                reason = "Liquidation fin de partie / saturation grange"
            elif norm >= 0.80:
                sell_qty = qty
                urgency = 0.85
                reason = f"Prix favorable ({norm:.2f}x base) : vente complète"
            else:
                sell_qty = 0
                urgency = 0.10
                reason = "Prix trop bas : conservation"

            if sell_qty > 0:
                result.append(
                    MarketProposal(
                        agent="market",
                        action="SELL",
                        product=product,
                        quantity=float(sell_qty),
                        priority=0.95 if norm >= 1.0 else 0.75,
                        urgency=urgency,
                        expected_value=sell_qty * price,
                        score=0.90,
                        reason=reason,
                        confidence=1.0,
                    )
                )

        return result