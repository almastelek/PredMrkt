"""Pydantic schemas for API request/response consistency and OpenAPI docs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --- Health ---
class HealthResponse(BaseModel):
    status: str = "ok"


# --- Error (consistent shape for 4xx/5xx) ---
class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Human-readable message")
    code: str | None = Field(None, description="Machine-readable code, e.g. no_events, not_found")


# --- Markets ---
class MarketListItem(BaseModel):
    market_id: str
    venue: str | None = None
    title: str | None = None
    category: str | None = None
    volume_24h: float | None = None
    liquidity: float | None = None
    active: bool | None = None
    outcomes: Any = None
    last_updated: int | None = None


class MarketsListResponse(BaseModel):
    markets: list[MarketListItem]
    total: int


# --- Events ---
class EventsStatsResponse(BaseModel):
    total_events: int
    min_ingest_ts: int | None
    max_ingest_ts: int | None
    by_market: list[dict[str, Any]]


class EventByMarketItem(BaseModel):
    market_id: str
    event_count: int
    title: str | None = None
    category: str | None = None
    sparkline: list[int] | None = None
    last_mid: float | None = Field(None, description="Last known mid price (probability) for this event")


# --- Market asset (event metadata + first outcome token) ---
class MarketAssetResponse(BaseModel):
    market_id: str
    asset_id: str
    title: str | None = None
    category: str | None = None


# --- Sim ---
class SimRunDetailResponse(BaseModel):
    run_id: str
    strategy_name: str
    market_id: str
    events_processed: int
    fill_count: int
    realized_pnl: float
    final_inventory: float
    params: dict[str, Any] = Field(default_factory=dict)
