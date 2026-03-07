"""Kalshi REST client - public market data (no auth required)."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from predexchange.ingestion.base import VenueConnector
from predexchange.models import Market, Outcome

log = structlog.get_logger(__name__)

KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiClient:
    """
    Read-only REST client for Kalshi events and markets.
    No authentication required for these endpoints.
    """

    def __init__(
        self,
        base_url: str = KALSHI_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    def get_events(
        self,
        limit: int = 200,
        cursor: str | None = None,
        status: str | None = None,
        series_ticker: str | None = None,
        with_nested_markets: bool = False,
        min_close_ts: int | None = None,
        min_updated_ts: int | None = None,
    ) -> dict[str, Any]:
        """GET /events. Returns { events: [...], cursor: str }."""
        params: dict[str, Any] = {"limit": min(max(1, limit), 200)}
        if cursor:
            params["cursor"] = cursor
        if status:
            params["status"] = status
        if series_ticker:
            params["series_ticker"] = series_ticker
        if with_nested_markets:
            params["with_nested_markets"] = "true"
        if min_close_ts is not None:
            params["min_close_ts"] = min_close_ts
        if min_updated_ts is not None:
            params["min_updated_ts"] = min_updated_ts
        return self._get("/events", params)

    def get_event(
        self,
        event_ticker: str,
        with_nested_markets: bool = False,
    ) -> dict[str, Any]:
        """GET /events/{event_ticker}. Returns single event object."""
        params = {}
        if with_nested_markets:
            params["with_nested_markets"] = "true"
        return self._get(f"/events/{event_ticker}", params if params else None)

    def get_markets(
        self,
        limit: int = 100,
        cursor: str | None = None,
        event_ticker: str | None = None,
        status: str | None = None,
        series_ticker: str | None = None,
        tickers: str | None = None,
    ) -> dict[str, Any]:
        """GET /markets. Returns { markets: [...], cursor: str }."""
        params: dict[str, Any] = {"limit": min(max(1, limit), 1000)}
        if cursor:
            params["cursor"] = cursor
        if event_ticker:
            params["event_ticker"] = event_ticker
        if status:
            params["status"] = status
        if series_ticker:
            params["series_ticker"] = series_ticker
        if tickers:
            params["tickers"] = tickers
        return self._get("/markets", params)

    def get_market(self, ticker: str) -> dict[str, Any]:
        """GET /markets/{ticker}. Returns single market object (unwrap from { market })."""
        data = self._get(f"/markets/{ticker}")
        return data.get("market", data)

    def get_orderbook(self, ticker: str) -> dict[str, Any]:
        """GET /markets/{ticker}/orderbook. Returns order book (yes/no bids)."""
        return self._get(f"/markets/{ticker}/orderbook")

    def get_candlesticks(
        self,
        series_ticker: str,
        ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int = 60,
        include_latest_before_start: bool = False,
    ) -> dict[str, Any]:
        """
        GET /series/{series_ticker}/markets/{ticker}/candlesticks.
        period_interval: 1 (1m), 60 (1h), or 1440 (1d).
        Timestamps in seconds.
        """
        if period_interval not in (1, 60, 1440):
            period_interval = 60
        params = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "period_interval": period_interval,
        }
        if include_latest_before_start:
            params["include_latest_before_start"] = "true"
        return self._get(
            f"/series/{series_ticker}/markets/{ticker}/candlesticks",
            params,
        )


def kalshi_market_to_canonical(raw: dict[str, Any]) -> Market:
    """Map Kalshi market response to canonical Market model."""
    ticker = str(raw.get("ticker", ""))
    title = str(raw.get("title", "") or raw.get("subtitle", ""))
    # Kalshi: yes_bid, yes_ask in cents (0-100); convert to [0,1]
    def cents_to_prob(c: Any) -> float:
        if c is None:
            return 0.5
        try:
            return float(c) / 100.0
        except (TypeError, ValueError):
            return 0.5

    yes_bid = cents_to_prob(raw.get("yes_bid"))
    yes_ask = cents_to_prob(raw.get("yes_ask"))
    last_price = cents_to_prob(raw.get("last_price"))
    # Binary market: single "Yes" outcome; use ticker as token_id for consistency
    outcomes = [
        Outcome(token_id=ticker, name="Yes", price=last_price or (yes_bid + yes_ask) / 2),
        Outcome(token_id=ticker, name="No", price=1.0 - (last_price or (yes_bid + yes_ask) / 2)),
    ]
    volume_24h = float(raw.get("volume_24h") or raw.get("volume_24h_fp") or 0)
    if isinstance(raw.get("volume_24h_fp"), str):
        try:
            volume_24h = float(raw["volume_24h_fp"])
        except (TypeError, ValueError):
            pass
    liquidity = float(raw.get("liquidity") or raw.get("liquidity_dollars") or 0)
    status = str(raw.get("status", "")).lower()
    active = status in ("open", "unopened", "")

    return Market(
        market_id=ticker,
        venue="kalshi",
        condition_id=None,
        question=title,
        title=title,
        category=raw.get("event_ticker"),
        volume_24h=volume_24h,
        liquidity=liquidity,
        active=active,
        outcomes=outcomes,
        last_updated=None,
        extra={
            "event_ticker": raw.get("event_ticker"),
            "status": raw.get("status"),
            "yes_bid": raw.get("yes_bid"),
            "yes_ask": raw.get("yes_ask"),
            "close_time": raw.get("close_time"),
        },
    )


class KalshiConnector(VenueConnector):
    """Kalshi connector: discovery via REST; WS ingestion not implemented."""

    venue_id = "kalshi"

    def __init__(self, client: KalshiClient | None = None) -> None:
        self._client = client or KalshiClient()

    def discover_markets(self, limit: int = 100, **kwargs: Any) -> list[Market]:
        """Fetch open Kalshi events with nested markets and return canonical Market list."""
        markets: list[Market] = []
        try:
            data = self._client.get_events(
                limit=min(limit, 200),
                status="open",
                with_nested_markets=True,
            )
            for ev in data.get("events") or []:
                for m in ev.get("markets") or []:
                    try:
                        markets.append(kalshi_market_to_canonical(m))
                    except Exception as e:
                        log.warning("skip_kalshi_market", ticker=m.get("ticker"), error=str(e))
                    if len(markets) >= limit:
                        return markets
        except Exception as e:
            log.warning("kalshi_discover_failed", error=str(e))
        return markets

    async def run_ingestion(
        self,
        asset_ids: list[str],
        on_message: Any,
        **kwargs: Any,
    ) -> None:
        """Kalshi REST-only for now; WS not implemented."""
        raise NotImplementedError("Kalshi WebSocket ingestion not implemented yet")
