"""Cheap deterministic counterfactual evaluator for candidate plans."""
def evaluate_plan(plan, state):
    base = float(getattr(plan, 'expected_profit', 0.0))
    prices = getattr(getattr(state, 'market', None), 'prices', {}) or {}
    # Approximate price exposure: selling plans are stressed by +/-15%.
    sell_value = sum(float(s.expected_revenue) for s in plan.steps if s.action == 'SELL')
    buy_cost = sum(float(s.estimated_cost) for s in plan.steps if s.action not in {'HARVEST','WATER','FEED','CARE','COLLECT_FERTILIZER'})
    best = base + 0.15 * sell_value
    worst = base - 0.15 * sell_value - 0.05 * buy_cost
    expected = 0.25 * best + 0.50 * base + 0.25 * worst
    return {'best': best, 'expected': expected, 'worst': worst, 'spread': best-worst}
