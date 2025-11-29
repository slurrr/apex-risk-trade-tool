from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PositionSizingResult:
    side: str
    size: float
    notional: float
    estimated_loss: float
    warnings: List[str]


class PositionSizingError(Exception):
    """Raised when sizing cannot be computed safely."""


def calculate_position_size(
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
    symbol_config: dict,
    slippage_factor: float = 0.0,
    fee_buffer_pct: float = 0.0,
) -> PositionSizingResult:
    """Placeholder pure sizing function. Logic will be implemented in US1."""
    raise PositionSizingError("Position sizing not yet implemented")
