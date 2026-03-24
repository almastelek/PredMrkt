"""Polymarket Data API client (public, no auth)."""

from __future__ import annotations

import time
from typing import Any

import httpx

DATA_API_BASE = "https://data-api.polymarket.com"


def _normalize_timestamp_ms(v: Any) -> int | None:
    """Normalize timestamp to milliseconds."""
    if v is None:
        return None
    try:
        ts = int(v)
    except (TypeError, ValueError):
        return None
    # Heuristic: if seconds, convert to ms.
    if ts < 10_000_000_000:
        ts *= 1000
    return ts


def normalize_trade(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Data API trade into storage-friendly shape."""
    size = float(raw.get("size") or 0.0)
    price = float(raw.get("price") or 0.0)
    ts_ms = _normalize_timestamp_ms(raw.get("timestamp")) or int(time.time() * 1000)
    return {
        "proxy_wallet": str(raw.get("proxyWallet") or "").lower(),
        "side": raw.get("side"),
        "asset": raw.get("asset"),
        "condition_id": raw.get("conditionId"),
        "size": size,
        "price": price,
        "notional_usdc": size * price,
        "timestamp_ms": ts_ms,
        "title": raw.get("title"),
        "slug": raw.get("slug"),
        "event_slug": raw.get("eventSlug"),
        "outcome": raw.get("outcome"),
        "transaction_hash": raw.get("transactionHash"),
    }


class PolymarketDataApiClient:
    """Thin client around Data API endpoints used by whale/insider feature."""

    def __init__(self, base_url: str = DATA_API_BASE, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        retries: int = 3,
        retry_backoff_sec: float = 1.0,
    ) -> Any:
        attempt = 0
        while True:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.get(f"{self.base_url}{path}", params=params)
                    # Retry transient gateway/timeouts/rate limit responses.
                    if r.status_code in (408, 429, 500, 502, 503, 504) and attempt < retries:
                        sleep_for = retry_backoff_sec * (2**attempt)
                        time.sleep(sleep_for)
                        attempt += 1
                        continue
                    r.raise_for_status()
                    return r.json()
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt >= retries:
                    raise
                sleep_for = retry_backoff_sec * (2**attempt)
                time.sleep(sleep_for)
                attempt += 1

    def get_trades(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        taker_only: bool = True,
        filter_type: str | None = None,
        filter_amount: float | None = None,
        markets: list[str] | None = None,
        event_ids: list[int] | None = None,
        user: str | None = None,
        side: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "limit": max(0, min(limit, 10000)),
            "offset": max(0, offset),
            "takerOnly": str(bool(taker_only)).lower(),
        }
        if filter_type is not None and filter_amount is not None:
            params["filterType"] = filter_type
            params["filterAmount"] = filter_amount
        if markets:
            params["market"] = ",".join(markets)
        if event_ids:
            params["eventId"] = ",".join(str(x) for x in event_ids)
        if user:
            params["user"] = user
        if side:
            params["side"] = side
        data = self._get("/trades", params)
        return data if isinstance(data, list) else []

    def get_positions(self, user: str) -> Any:
        return self._get("/positions", {"user": user})

    def get_closed_positions(self, user: str) -> Any:
        return self._get("/closed-positions", {"user": user})

    def get_activity(self, user: str) -> Any:
        return self._get("/activity", {"user": user})

    def get_value(self, user: str) -> Any:
        return self._get("/value", {"user": user})

