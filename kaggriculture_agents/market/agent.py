"""MarketAgent — marché dynamique et ventes opportunistes."""
from collections import deque
from dataclasses import replace
from typing import Dict, List

from .analyzers import analyze_prices, find_hold_opportunities, find_production_opportunities, find_sell_opportunities
from .models import MarketProposal, PriceAnalysis
from .constants import MARKET_PRODUCT_INFO, MARKET_CURVE_PARAMS
from .demand import build_demand_forecast


class MarketAgent:
    """Analyse le marché et transforme prix + tendance en décisions de vente.

    Le marché du jeu évolue avec l'inventaire. Les captures du leader montrent
    des ventes/réinvestissements par vagues plutôt qu'une liquidation aveugle.
    Cet agent conserve donc une courte mémoire EMA des prix entre les tours.
    """

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
            q = self._history.setdefault(product, deque(maxlen=self._history_size))
            if not q or q[-1] != price:
                q.append(float(price))
            previous_ema = self._ema.get(product, float(price))
            self._ema[product] = 0.80 * previous_ema + 0.20 * float(price)

            inv = float(state.market.inventory.get(product, 10000.0))
            iq = self._inventory_history.setdefault(product, deque(maxlen=self._history_size))
            if not iq or iq[-1] != inv:
                iq.append(inv)

    @staticmethod
    def _robust_slope(values) -> float:
        values = list(values)[-8:]
        if len(values) < 2:
            return 0.0
        # Régression linéaire locale puis clamp robuste : un point aberrant
        # ne peut pas faire varier la prévision de plus de 1/12 du prix de base.
        n = len(values)
        xbar = (n - 1) / 2.0
        ybar = sum(values) / n
        denom = sum((i - xbar) ** 2 for i in range(n))
        if denom <= 0:
            return 0.0
        slope = sum((i - xbar) * (y - ybar) for i, y in enumerate(values)) / denom
        return slope

    @staticmethod
    def _curve_value(product: str, inventory: float) -> float:
        params = MARKET_CURVE_PARAMS.get(product)
        if not params:
            return float(MARKET_PRODUCT_INFO.get(product, {}).get("base_price", 0.0))
        base = params["base"]
        I0 = params["I0"]
        T = max(1.0, params["T"])
        below = inventory < I0
        func = params["below_func"] if below else params["above_func"]
        target = params["below_target"] if below else params["above_target"]
        x = abs(inventory - I0)

        import math
        def f(v):
            if func == "linear": return v
            if func == "sq": return v * v
            if func == "sqrt": return math.sqrt(v)
            if func == "log": return math.log1p(v)
            if func == "log10": return math.log10(1.0 + v)
            return v
        ft = max(1e-12, f(T))
        amp = target * base / ft
        value = base + (amp * f(x) if below else -amp * f(x))
        return max(1.0, round(value))

    def _forecast(self, state, product: str):
        price = float(state.market.prices.get(product, 0.0))
        base = float(MARKET_PRODUCT_INFO.get(product, {}).get("base_price", price or 1.0))
        inv = float(state.market.inventory.get(product, 10000.0))
        prior_inv = self._last_inventory.get(product, inv)
        own_flow = self._pending_market_flow.get(product, 0.0)
        external_delta = (inv - prior_inv) - own_flow
        drift = external_delta
        # Quand plusieurs observations sont disponibles, lissage léger du drift.
        iq = self._inventory_history.get(product)
        if iq and len(iq) >= 2:
            recent = list(iq)[-4:]
            deltas = [recent[i] - recent[i-1] for i in range(1, len(recent))]
            if deltas:
                drift = 0.5 * drift + 0.5 * (sum(deltas) / len(deltas))

        slope = self._robust_slope(self._history.get(product, ()))
        slope = max(-base / 12.0, min(base / 12.0, slope))
        ema = self._ema.get(product, price)

        demand = build_demand_forecast(state)
        demand_pressure = demand.demand_units.get(product, 1.0) - demand.opponent_supply_pressure.get(product, 0.0)
        # Le drift de demande est converti en une petite correction d'inventaire
        # journalière : la demande réduit l'inventaire, la production adverse l'augmente.
        demand_correction = max(-8.0, min(8.0, demand_pressure * 0.25))

        projections = {}
        prices = {}
        for horizon in (1, 3, 7):
            projected_inv = max(1.0, inv + (drift - demand_correction) * horizon)
            analytic = self._curve_value(product, projected_inv)
            momentum = max(1.0, ema + slope * horizon)
            predicted = max(1.0, round(0.75 * analytic + 0.25 * momentum))
            projections[horizon] = projected_inv
            prices[horizon] = predicted

        self._last_inventory[product] = inv
        self._pending_market_flow[product] = 0.0
        return {
            "ema": ema, "slope": slope, "drift": drift,
            "inv1": projections[1], "inv3": projections[3], "inv7": projections[7],
            "p1": prices[1], "p3": prices[3], "p7": prices[7],
            "forecast_factor": prices[3] / max(1.0, base),
        }

    def _trend(self, product: str) -> float:
        q = self._history.get(product)
        if not q or len(q) < 2:
            return 0.0
        recent = list(q)[-4:]
        if len(recent) < 2 or recent[0] == 0:
            return 0.0
        return (recent[-1] - recent[0]) / recent[0]

    def decide(self, state) -> List[MarketProposal]:
        self._record_prices(state)
        base_analyses = self.analyze_prices(state)
        forecast_by_product = {product: self._forecast(state, product) for product in sorted(state.market.prices)}
        price_analyses = [
            replace(a,
                    ema_price=forecast_by_product[a.product]["ema"],
                    robust_slope=forecast_by_product[a.product]["slope"],
                    inventory_drift=forecast_by_product[a.product]["drift"],
                    projected_inventory_1d=forecast_by_product[a.product]["inv1"],
                    projected_inventory_3d=forecast_by_product[a.product]["inv3"],
                    projected_inventory_7d=forecast_by_product[a.product]["inv7"],
                    forecast_price_1d=forecast_by_product[a.product]["p1"],
                    forecast_price_3d=forecast_by_product[a.product]["p3"],
                    forecast_price_7d=forecast_by_product[a.product]["p7"],
                    expected_price_factor=forecast_by_product[a.product]["forecast_factor"])
            for a in base_analyses
        ]
        proposals: List[MarketProposal] = []
        proposals += find_sell_opportunities(state, price_analyses)
        proposals += find_hold_opportunities(state, price_analyses)
        proposals += find_production_opportunities(state, price_analyses)
        proposals = self._dynamic_sales(state, proposals, price_analyses)
        emitted_flow: Dict[str, float] = {}
        for proposal in proposals:
            if proposal.action == "SELL" and proposal.product:
                emitted_flow[proposal.product] = emitted_flow.get(proposal.product, 0.0) + float(proposal.quantity or 0.0)
            elif proposal.action == "BUY_PRODUCT" and proposal.product:
                emitted_flow[proposal.product] = emitted_flow.get(proposal.product, 0.0) - float(proposal.quantity or 0.0)
        self._pending_market_flow = emitted_flow
        return self._sort_proposals(proposals)

    @staticmethod
    def analyze_prices(state) -> List[PriceAnalysis]:
        return analyze_prices(state)

    def _dynamic_sales(self, state, proposals: List[MarketProposal], analyses: List[PriceAnalysis]) -> List[MarketProposal]:
        """Remplace les ventes statiques par une politique prix+tendance.

        - prix >= 1.15x base : vente forte (70-100% du stock) ;
        - prix 1.05-1.15x : vente partielle, davantage si la tendance baisse ;
        - prix < 0.90x avec tendance positive : HOLD ;
        - prix intermédiaire + tendance baissière : vente préventive partielle ;
        - fin de partie / shed plein : liquidation prioritaire.
        """
        by_product: Dict[str, List[MarketProposal]] = {}
        for p in proposals:
            if p.action in ("SELL", "HOLD"):
                by_product.setdefault(p.product, []).append(p)

        result = [p for p in proposals if p.action not in ("SELL", "HOLD")]
        for product, quantity in state.resources.shed.items():
            qty = int(quantity)
            if qty <= 0 or product not in state.market.prices:
                continue
            # Ne jamais vider le buffer de fertilisant : il sert à la boucle
            # animale/culturelle et son remplacement au marché est coûteux.
            if product == "FERTILIZER" and qty <= 2:
                continue
            info = MARKET_PRODUCT_INFO.get(product)
            if not info:
                continue
            price = float(state.market.prices[product])
            base = float(info["base_price"])
            norm = price / base if base else 1.0
            trend = self._trend(product)
            analysis = next((a for a in analyses if a.product == product), None)
            demand = analysis.demand_score if analysis else 0.0
            expected_factor = analysis.expected_price_factor if analysis else norm
            forecast_1 = analysis.forecast_price_1d if analysis else price
            forecast_3 = analysis.forecast_price_3d if analysis else price
            forecast_7 = analysis.forecast_price_7d if analysis else price
            forecast_trend = (forecast_3 - price) / max(1.0, price)

            if state.time.remaining_days <= 1 or state.risks.shed_near_capacity:
                sell_qty = qty
                urgency = 0.95
                reason = f"liquidation obligatoire : fin de partie/pression du shed, prix {price:.0f}$"
            elif norm >= 1.15:
                # Une forte demande permet de vendre, mais on évite de vider
                # tout le stock lorsque la rareté future est encore plus forte.
                sell_ratio = 0.70 if demand >= 0.70 and expected_factor >= norm else 1.0
                sell_qty = max(1, int(round(qty * sell_ratio)))
                urgency = 0.85
                reason = f"prix élevé {price:.0f}$ ({norm:.2f}x base), demande {demand:.2f} : vente contrôlée"
            elif norm >= 1.05:
                sell_qty = max(1, int(round(qty * (0.80 if forecast_trend <= 0 else 0.45))))
                urgency = 0.70
                reason = (f"prix favorable {price:.0f}$ ({norm:.2f}x base), "
                          f"prévision J+3 {forecast_3:.0f}$ ({forecast_trend:+.1%}) : vente partielle")
            elif norm >= 0.90 and (trend < -0.02 or forecast_trend < -0.03):
                sell_qty = max(1, int(round(qty * 0.40)))
                urgency = 0.60
                reason = f"prix moyen {price:.0f}$ mais tendance baissière {trend:+.1%} : vente préventive"
            elif norm < 0.90 and (trend > 0.01 or forecast_trend > 0.02):
                sell_qty = 0
                urgency = 0.20
                reason = (f"prix faible {price:.0f}$, mais prévision J+3 {forecast_3:.0f}$ "
                          f"({forecast_trend:+.1%}) : conserver")
            else:
                sell_qty = 0
                urgency = 0.15
                reason = f"prix {price:.0f}$ sans signal de vente fort : conserver"

            if sell_qty > 0:
                expected = sell_qty * price
                score = min(1.0, 0.45 * min(1.0, norm / 1.5) + 0.20 * min(1.0, sell_qty / 20.0) + 0.15 * min(1.0, max(0.0, -trend) * 10.0) + 0.20 * demand)
                result.append(MarketProposal(
                    agent="market", action="SELL", product=product, quantity=float(sell_qty),
                    priority=0.95 if norm >= 1.15 else 0.72, urgency=urgency,
                    expected_value=expected, score=score, reason=reason, confidence=1.0,
                ))
            # HOLD reste un signal interne : aucune proposition HOLD n'est
            # émise. L'absence de SELL est déjà l'action "conserver" et le
            # Planner ne doit pas consacrer de budget de calcul à une action
            # non exécutable.
        return result

    @staticmethod
    def _sort_proposals(proposals: List[MarketProposal]) -> List[MarketProposal]:
        return sorted(proposals, key=lambda p: (-p.score, -p.urgency, p.action, p.product))
