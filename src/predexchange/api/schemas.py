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


# --- Event compare (Polymarket <-> Kalshi pairs) ---
class ComparePairItem(BaseModel):
    id: int
    label: str | None = None
    polymarket_market_id: str
    polymarket_asset_id: str | None = None
    kalshi_event_ticker: str
    kalshi_market_ticker: str
    polymarket_title: str | None = None
    kalshi_title: str | None = None


class CompareListResponse(BaseModel):
    pairs: list[ComparePairItem]


class CompareDetailResponse(BaseModel):
    id: int
    label: str | None = None
    polymarket_market_id: str
    polymarket_asset_id: str | None = None
    kalshi_event_ticker: str
    kalshi_market_ticker: str
    polymarket: dict[str, Any] = Field(default_factory=dict, description="Polymarket market metadata if available")
    kalshi: dict[str, Any] = Field(default_factory=dict, description="Kalshi market metadata from API")


# --- Event compare candidates (Phase 4: suggested pairs for admin approve/reject) ---
class CompareCandidateItem(BaseModel):
    score: float
    polymarket_market_id: str
    polymarket_title: str | None = None
    kalshi_event_ticker: str
    kalshi_market_ticker: str
    kalshi_title: str | None = None
    kalshi_strike_ts: int | None = None


class CompareCandidatesResponse(BaseModel):
    candidates: list[CompareCandidateItem]


class ApprovePairRequest(BaseModel):
    polymarket_market_id: str
    kalshi_event_ticker: str
    kalshi_market_ticker: str
    polymarket_asset_id: str | None = None
    label: str | None = None


class RejectCandidateRequest(BaseModel):
    polymarket_market_id: str
    kalshi_market_ticker: str


# --- Whales / wallets ---
class WhaleTrade(BaseModel):
    wallet: str
    side: str | None = None
    condition_id: str | None = None
    title: str | None = None
    outcome: str | None = None
    size: float | None = None
    price: float | None = None
    notional_usdc: float | None = None
    timestamp_ms: int
    transaction_hash: str | None = None


class WhaleTradesResponse(BaseModel):
    trades: list[WhaleTrade]


class WhaleWalletAgg(BaseModel):
    wallet: str
    spend_1d: float
    spend_7d: float
    spend_30d: float
    first_seen_ms: int | None = None
    last_seen_ms: int | None = None
    active_days: int
    top_market_notional_30d: float
    top_market_concentration_30d: float
    is_tracked: bool | None = None


class WhaleWalletsResponse(BaseModel):
    wallets: list[WhaleWalletAgg]


class TrackedWallet(BaseModel):
    address: str
    label: str | None = None
    notes: str | None = None
    created_at_ms: int


class TrackedWalletsResponse(BaseModel):
    wallets: list[TrackedWallet]


class TrackWalletRequest(BaseModel):
    address: str
    label: str | None = None
    notes: str | None = None


class WalletDetailResponse(BaseModel):
    wallet: str
    summary: WhaleWalletAgg | None = None
    tracked: TrackedWallet | None = None


class WalletLiveResponse(BaseModel):
    wallet: str
    value: Any = None
    positions: Any = None
    closed_positions: Any = None
    activity: Any = None
