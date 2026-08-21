"""Adversarial stress tests for plans. No environment mutation."""
from dataclasses import dataclass
@dataclass(frozen=True)
class StressResult:
    scenario: str
    score: float
    message: str

def stress_test(state, plan):
    base=float(plan.expected_profit)
    sells=sum(float(s.expected_revenue) for s in plan.steps if s.action=='SELL')
    buys=sum(float(s.estimated_cost) for s in plan.steps if s.action in {'BUY_SEED','BUY_ANIMAL','BUY_LAND','BUILD_COOP','BUILD_PASTURE','HIRE'})
    results=[]
    for name, shock in [('PRICE_-15%',-0.15),('PRICE_+15%',0.15),('COST_+10%',-0.10)]:
        score=base + sells*shock - buys*(0.10 if name=='COST_+10%' else 0.0)
        results.append(StressResult(name,score,f"stress score={score:.1f}"))
    return tuple(results)
