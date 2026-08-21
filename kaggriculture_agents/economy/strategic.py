"""Strategic economic layer: shadow prices, marginal labor and terminal value."""
from dataclasses import dataclass
from math import exp

@dataclass(frozen=True)
class StrategicEconomy:
    shadow_prices: dict
    terminal_wealth: float
    reserved_cash: float
    marginal_worker_values: tuple
    risk_budget: float


def _get(d, k, default=0.0):
    try: return float(d.get(k, default))
    except Exception: return float(default)


def build_strategic_economy(state, horizon_days=7):
    money = _get(getattr(state.resources, 'money', {}), 'money', getattr(state.resources, 'money', 0.0))
    # Preserve cash for feed, survival and the next high-value investment.
    animals = getattr(state, 'animals', None)
    animal_count = 0
    if animals is not None:
        try: animal_count = len(animals)
        except Exception: pass
    wheat = _get(getattr(state.resources, 'shed', {}), 'WHEAT')
    feed_reserve = animal_count * max(1, horizon_days)
    reserve = max(money * 0.18, feed_reserve * 31.0)

    prices = getattr(state.market, 'prices', {})
    shadow = {k: float(v) for k, v in prices.items()}
    # Inputs with operational scarcity receive an internal premium.
    if wheat < feed_reserve:
        shadow['WHEAT'] = max(shadow.get('WHEAT', 31.0), shadow.get('WHEAT', 31.0) * 1.35)
    fert = _get(getattr(state.resources, 'shed', {}), 'FERTILIZER')
    if fert <= 1:
        shadow['FERTILIZER'] = max(shadow.get('FERTILIZER', 100.0), 125.0)

    # Existing stock has option value when a high-price harvest is imminent.
    for product, p in list(shadow.items()):
        shadow[product] = round(max(1.0, p), 2)

    # Worker marginal value decays with the Fibonacci-like daily hiring cost.
    # We use the documented cost sequence 1,1,2,3,5,8,... and a conservative
    # estimate based on remaining non-idle capacity.
    remaining = max(1, int(getattr(getattr(state, 'time', None), 'remaining_days', 1)))
    base_action_value = max(10.0, sum(shadow.values()) / max(1, len(shadow)))
    fib = [1,1]
    while len(fib) < 8: fib.append(fib[-1] + fib[-2])
    worker_values = tuple(round(base_action_value * min(3.0, 1.0 + 0.15 * min(remaining, 10)) / c, 2) for c in fib)

    terminal = money + max(0.0, base_action_value * min(10.0, remaining))
    risk_budget = max(0.0, min(1.0, 0.12 + 0.015 * min(remaining, 20)))
    return StrategicEconomy(shadow, terminal, reserve, worker_values, risk_budget)
