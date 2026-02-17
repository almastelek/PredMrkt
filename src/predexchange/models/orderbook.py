"""OrderBookSnapshot, OrderBookDelta - canonical orderbook."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PriceLevel(BaseModel):
    """Single price level (price -> size)."""

    price: float = Field(..., ge=0, le=1)
    size: float = Field(..., ge=0)


class OrderBookSnapshot(BaseModel):
    """Full L2 orderbook snapshot."""

    market_id: str
    asset_id: str
    venue: str = "polymarket"
    bids: list[PriceLevel] = Field(default_factory=list)
    asks: list[PriceLevel] = Field(default_factory=list)
    exchange_ts: int | None = None  # ms epoch
    ingest_ts: int | None = None


class OrderBookDelta(BaseModel):
    """Incremental orderbook update (e.g. price_change)."""

    market_id: str
    asset_id: str
    venue: str = "polymarket"
    side: str = Field(..., pattern="^(BUY|SELL)$")
    price: float = Field(..., ge=0, le=1)
    size: float = Field(..., ge=0)
    exchange_ts: int | None = None
    ingest_ts: int | None = None
    # Optional best bid/ask after this change (for validation)
    best_bid: float | None = None
    best_ask: float | None = None
