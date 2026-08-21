from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass(frozen=True)
class InvestmentProposal:
    """Intention d'investissement; jamais une action Kaggriculture directe."""
    action: str
    product: Optional[str] = None
    target: Optional[Tuple[int, int]] = None
    quantity: int = 1
    cost: float = 0.0
    expected_revenue: float = 0.0
    expected_profit: float = 0.0
    urgency: float = 0.5
    score: float = 0.0
    confidence: float = 1.0
    reason: str = ""
    dependencies: Tuple[str, ...] = ()
