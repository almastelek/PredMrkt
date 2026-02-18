"""Polymarket Gamma API client - market discovery and metadata."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import structlog

from predexchange.models import Market, Outcome

log = structlog.get_logger(__name__)

GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"


def _parse_outcomes(
    outcomes_str: str | list[str],
    prices_str: str | list[str] | None,
    clob_token_ids_str: str | list[str] | None,
) -> list[Outcome]:
    """Build Outcome list from Gamma API outcome fields (may be JSON strings)."""
    if isinstance(outcomes_str, list):
        names = outcomes_str
    else:
        try:
            names = json.loads(outcomes_str) if outcomes_str else []
        except (json.JSONDecodeError, TypeError):
            names = []
    if isinstance(prices_str, list):
        prices = [float(p) for p in prices_str]
    elif prices_str:
        try:
            prices = [float(p) for p in json.loads(prices_str)]
        except (json.JSONDecodeError, TypeError):
            prices = [0.0] * len(names)
    else:
        prices = [0.0] * len(names)
    if isinstance(clob_token_ids_str, list):
        token_ids = clob_token_ids_str
    elif clob_token_ids_str:
        try:
            token_ids = json.loads(clob_token_ids_str)
        except (json.JSONDecodeError, TypeError):
            token_ids = [""] * len(names)
    else:
        token_ids = [""] * len(names)
    # Align lengths
    while len(prices) < len(names):
        prices.append(0.0)
    while len(token_ids) < len(names):
        token_ids.append("")
    return [
        Outcome(token_id=tid, name=name, price=price)
        for name, price, tid in zip(names, prices, token_ids)
    ]


def parse_market(raw: dict[str, Any], venue: str = "polymarket") -> Market:
    """Convert Gamma API market object to canonical Market."""
    from predexchange.storage.event_log import normalize_condition_id

    condition_id = normalize_condition_id(
        str(raw.get("conditionId") or raw.get("condition_id") or "")
    )
    market_id = condition_id or str(raw.get("id", ""))
    volume_24h = float(raw.get("volume24hr") or raw.get("volume24hr") or raw.get("volume", 0) or 0)
    liquidity = float(raw.get("liquidity") or raw.get("liquidityNum") or 0)
    outcomes = _parse_outcomes(
        raw.get("outcomes", "[]"),
        raw.get("outcomePrices"),
        raw.get("clobTokenIds"),
    )
    return Market(
        market_id=market_id,
        venue=venue,
        condition_id=condition_id or None,
        question=raw.get("question", ""),
        title=raw.get("question", "") or raw.get("title", ""),
        category=raw.get("category"),
        volume_24h=volume_24h,
        liquidity=liquidity,
        active=bool(raw.get("active", True) and not raw.get("closed", False)),
        outcomes=outcomes,
        last_updated=int(time.time() * 1000),
        extra={"gamma_id": raw.get("id"), "slug": raw.get("slug")},
    )


def fetch_markets(
    base_url: str | None = None,
    limit: int = 200,
    active_only: bool = True,
    timeout: float = 30.0,
) -> list[Market]:
    """Fetch markets from Gamma API and return canonical Market list."""
    base = (base_url or GAMMA_MARKETS_URL).rstrip("/")
    url = base if "/markets" in base else base + "/markets"
    params = {"limit": limit}
    if active_only:
        params["closed"] = "false"
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, list):
        data = data.get("data", data) if isinstance(data, dict) else []
    markets = []
    for row in data:
        if active_only and (row.get("closed") is True or row.get("active") is False):
            continue
        try:
            markets.append(parse_market(row))
        except Exception as e:
            log.warning("skip_market", market_id=row.get("conditionId"), error=str(e))
    return markets


def select_top_markets(
    markets: list[Market],
    track_count: int,
    min_volume_24h: float = 0,
    min_liquidity: float = 0,
    category_allowlist: list[str] | None = None,
    category_denylist: list[str] | None = None,
    pinned_market_ids: list[str] | None = None,
    active_only: bool = True,
) -> list[Market]:
    """Select top markets by volume/activity with optional filters and pinned set."""
    pinned_market_ids = pinned_market_ids or []
    allow = set((category_allowlist or []))
    deny = set((category_denylist or []))

    def allowed(m: Market) -> bool:
        if active_only and not m.active:
            return False
        if m.volume_24h < min_volume_24h or m.liquidity < min_liquidity:
            return False
        if m.category and deny and m.category in deny:
            return False
        if m.category and allow and m.category not in allow:
            return False
        return True

    filtered = [m for m in markets if allowed(m)]
    # Sort by volume_24h desc, then liquidity desc
    filtered.sort(key=lambda m: (m.volume_24h, m.liquidity), reverse=True)
    selected_ids = set()
    selected: list[Market] = []
    for mid in pinned_market_ids:
        for m in filtered:
            if m.market_id == mid and m.market_id not in selected_ids:
                selected.append(m)
                selected_ids.add(m.market_id)
                break
    for m in filtered:
        if len(selected) >= track_count:
            break
        if m.market_id not in selected_ids:
            selected.append(m)
            selected_ids.add(m.market_id)
    return selected
