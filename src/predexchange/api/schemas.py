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


# --- Signals: episodes, stats, alerts ---
class WalletEpisode(BaseModel):
    episode_id: str
    wallet: str
    condition_id: str
    outcome: str | None = None
    asset_id: str | None = None
    market_slug: str | None = None
    event_slug: str | None = None
    title: str | None = None
    episode_start_ms: int
    episode_end_ms: int
    trade_count: int
    buy_count: int
    sell_count: int
    gross_notional_usdc: float
    net_notional_usdc: float
    avg_fill_price: float | None = None
    vwap_price: float | None = None
    max_single_fill_usdc: float | None = None
    market_category: str | None = None
    mins_to_event_start: float | None = None
    mins_to_resolution: float | None = None
    px_t0: float | None = None
    px_fwd_1h: float | None = None
    px_fwd_6h: float | None = None
    px_fwd_24h: float | None = None
    ret_1h: float | None = None
    ret_6h: float | None = None
    ret_24h: float | None = None


class WalletEpisodesResponse(BaseModel):
    episodes: list[WalletEpisode]


class WalletSignalStats(BaseModel):
    wallet: str
    asof_ms: int
    episodes_30d: int
    gross_notional_30d: float
    concentration_top_market_30d: float
    active_days_30d: int
    hitrate_24h_90d: float | None = None
    avg_ret_24h_90d: float | None = None
    sharpe_like_90d: float | None = None
    edge_consistency_90d: float | None = None
    sports_share_30d: float
    non_sports_share_30d: float
    historical_episode_count: int


class WalletSignalStatsResponse(BaseModel):
    stats: WalletSignalStats | None = None


class SignalAlert(BaseModel):
    alert_id: str
    episode_id: str
    wallet: str
    condition_id: str | None = None
    market_category: str | None = None
    scored_at_ms: int
    base_edge_score: float
    context_adjusted_score: float
    insider_likelihood_score: float
    factor_timing: float | None = None
    factor_size: float | None = None
    factor_concentration: float | None = None
    factor_history: float | None = None
    factor_coordination: float | None = None
    factor_sports_penalty: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    review_status: str = "new"
    title: str | None = None
    outcome: str | None = None
    gross_notional_usdc: float | None = None
    episode_end_ms: int | None = None


class SignalAlertsResponse(BaseModel):
    alerts: list[SignalAlert]


class SignalsRunResponse(BaseModel):
    episodes_upserted: int
    market_meta_updated: int
    forward_returns_filled: int
    wallet_stats_upserted: int
    alerts_scored: int
