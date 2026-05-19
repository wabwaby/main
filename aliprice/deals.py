"""Deal detection heuristics for tracked price history."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Optional

from .storage import PricePoint, Product


@dataclass
class DealSignal:
    """A summary of how good the current price is for a product."""

    product: Product
    current_price: float
    currency: Optional[str]
    previous_price: Optional[float]
    lowest_price: float
    average_price: float
    samples: int

    drop_vs_previous_pct: Optional[float]
    drop_vs_average_pct: float
    drop_vs_lowest_pct: float
    is_all_time_low: bool

    @property
    def is_deal(self) -> bool:
        """Heuristic for what counts as a "real" deal worth surfacing."""
        if self.samples < 2:
            return False
        if self.is_all_time_low and self.drop_vs_average_pct >= 5:
            return True
        if self.drop_vs_average_pct >= 10:
            return True
        if (
            self.drop_vs_previous_pct is not None
            and self.drop_vs_previous_pct >= 8
        ):
            return True
        return False

    @property
    def headline(self) -> str:
        parts = []
        if self.is_all_time_low:
            parts.append("ALL-TIME LOW")
        if self.drop_vs_average_pct >= 10:
            parts.append(f"{self.drop_vs_average_pct:.1f}% below avg")
        if (
            self.drop_vs_previous_pct is not None
            and self.drop_vs_previous_pct >= 5
        ):
            parts.append(f"{self.drop_vs_previous_pct:.1f}% drop since last check")
        return " · ".join(parts) if parts else "no significant change"


def evaluate(product: Product, history: list[PricePoint]) -> Optional[DealSignal]:
    """Build a :class:`DealSignal` for a product. Returns ``None`` if no data."""
    if not history:
        return None
    prices = [p.price for p in history]
    current = prices[-1]
    previous = prices[-2] if len(prices) >= 2 else None
    lowest = min(prices)
    avg = mean(prices)

    drop_vs_previous_pct: Optional[float] = None
    if previous and previous > 0:
        drop_vs_previous_pct = (previous - current) / previous * 100

    drop_vs_average_pct = (avg - current) / avg * 100 if avg > 0 else 0.0
    drop_vs_lowest_pct = (lowest - current) / lowest * 100 if lowest > 0 else 0.0

    return DealSignal(
        product=product,
        current_price=current,
        currency=history[-1].currency or product.currency,
        previous_price=previous,
        lowest_price=lowest,
        average_price=avg,
        samples=len(prices),
        drop_vs_previous_pct=drop_vs_previous_pct,
        drop_vs_average_pct=drop_vs_average_pct,
        drop_vs_lowest_pct=drop_vs_lowest_pct,
        is_all_time_low=current <= lowest,
    )
