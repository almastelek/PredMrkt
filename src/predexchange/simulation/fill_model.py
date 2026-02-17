"""Touch-fill simulator: fill when market crosses quote, with optional latency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Fill:
    """A simulated fill."""

    market_id: str
    asset_id: str
    side: str
    price: float
    size: float
    timestamp: int


class TouchFillModel:
    """Fill when mid price crosses the quote (bid for sells, ask for buys). Configurable latency (ms)."""

    def __init__(self, latency_ms: int = 0) -> None:
        self.latency_ms = latency_ms

    def check_fill(
        self,
        side: str,
        quote_price: float,
        quote_size: float,
        mid_price: float,
        timestamp: int,
        market_id: str = "",
        asset_id: str = "",
    ) -> Fill | None:
        """If market crossed quote, return a Fill; else None."""
        if side == "BUY" and mid_price <= quote_price and quote_size > 0:
            return Fill(
                market_id=market_id,
                asset_id=asset_id,
                side=side,
                price=quote_price,
                size=quote_size,
                timestamp=timestamp + self.latency_ms,
            )
        if side == "SELL" and mid_price >= quote_price and quote_size > 0:
            return Fill(
                market_id=market_id,
                asset_id=asset_id,
                side=side,
                price=quote_price,
                size=quote_size,
                timestamp=timestamp + self.latency_ms,
            )
        return None
