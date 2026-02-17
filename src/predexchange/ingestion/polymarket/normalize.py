"""Polymarket WS message -> canonical OrderBookSnapshot / OrderBookDelta / TradePrint."""

from __future__ import annotations

from typing import Any

from predexchange.models.orderbook import OrderBookDelta, OrderBookSnapshot, PriceLevel
from predexchange.models.trade import TradePrint


def _float(s: str | float | None) -> float:
    if s is None:
        return 0.0
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def parse_book_message(payload: dict[str, Any]) -> OrderBookSnapshot | None:
    """Convert Polymarket 'book' message to OrderBookSnapshot. Uses 'bids'/'asks' or 'buys'/'sells'."""
    if payload.get("event_type") != "book":
        return None
    market_id = str(payload.get("market") or payload.get("market_id") or "")
    asset_id = str(payload.get("asset_id") or "")
    if not market_id or not asset_id:
        return None
    bids_raw = payload.get("bids") or payload.get("buys") or []
    asks_raw = payload.get("asks") or payload.get("sells") or []
    bids = []
    for lev in bids_raw:
        if isinstance(lev, dict):
            p, s = _float(lev.get("price")), _float(lev.get("size"))
        else:
            continue
        if 0 <= p <= 1 and s >= 0:
            bids.append(PriceLevel(price=p, size=s))
    asks = []
    for lev in asks_raw:
        if isinstance(lev, dict):
            p, s = _float(lev.get("price")), _float(lev.get("size"))
        else:
            continue
        if 0 <= p <= 1 and s >= 0:
            asks.append(PriceLevel(price=p, size=s))
    ts = payload.get("timestamp")
    exchange_ts = int(ts) if ts is not None else None
    try:
        if isinstance(exchange_ts, str):
            exchange_ts = int(exchange_ts)
    except (TypeError, ValueError):
        exchange_ts = None
    return OrderBookSnapshot(
        market_id=market_id,
        asset_id=asset_id,
        bids=bids,
        asks=asks,
        exchange_ts=exchange_ts,
        ingest_ts=None,
    )


def parse_price_change_message(payload: dict[str, Any]) -> list[OrderBookDelta]:
    """Convert Polymarket 'price_change' message to one or more OrderBookDeltas (one per price_changes entry)."""
    if payload.get("event_type") != "price_change":
        return []
    market_id = str(payload.get("market") or payload.get("market_id") or "")
    ts = payload.get("timestamp")
    exchange_ts = int(ts) if ts is not None else None
    if isinstance(exchange_ts, str):
        try:
            exchange_ts = int(exchange_ts)
        except (TypeError, ValueError):
            exchange_ts = None
    changes = payload.get("price_changes") or []
    out = []
    for pc in changes:
        if not isinstance(pc, dict):
            continue
        asset_id = str(pc.get("asset_id") or "")
        side = (pc.get("side") or "BUY").upper()
        if side not in ("BUY", "SELL"):
            continue
        price = _float(pc.get("price"))
        size = _float(pc.get("size"))
        best_bid = _float(pc.get("best_bid")) if pc.get("best_bid") is not None else None
        best_ask = _float(pc.get("best_ask")) if pc.get("best_ask") is not None else None
        out.append(
            OrderBookDelta(
                market_id=market_id,
                asset_id=asset_id,
                side=side,
                price=price,
                size=size,
                exchange_ts=exchange_ts,
                ingest_ts=None,
                best_bid=best_bid or None,
                best_ask=best_ask or None,
            )
        )
    return out


def parse_last_trade_message(payload: dict[str, Any]) -> TradePrint | None:
    """Convert Polymarket 'last_trade_price' message to TradePrint."""
    if payload.get("event_type") != "last_trade_price":
        return None
    market_id = str(payload.get("market") or payload.get("market_id") or "")
    asset_id = str(payload.get("asset_id") or "")
    side = (payload.get("side") or "BUY").upper()
    if side not in ("BUY", "SELL"):
        return None
    ts = payload.get("timestamp")
    try:
        exchange_ts = int(ts) if ts is not None else None
    except (TypeError, ValueError):
        exchange_ts = None
    return TradePrint(
        market_id=market_id,
        asset_id=asset_id,
        side=side,
        price=_float(payload.get("price")),
        size=_float(payload.get("size")),
        exchange_ts=exchange_ts,
        ingest_ts=None,
        fee_rate_bps=int(payload.get("fee_rate_bps") or 0),
    )
