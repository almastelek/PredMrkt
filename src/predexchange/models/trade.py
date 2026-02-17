"""TradePrint - canonical trade."""

from pydantic import BaseModel, Field


class TradePrint(BaseModel):
    """Executed trade (last_trade_price / trade print)."""

    market_id: str
    asset_id: str
    venue: str = "polymarket"
    side: str = Field(..., pattern="^(BUY|SELL)$")
    price: float = Field(..., ge=0, le=1)
    size: float = Field(..., ge=0)
    exchange_ts: int | None = None  # ms epoch
    ingest_ts: int | None = None
    fee_rate_bps: int = 0
