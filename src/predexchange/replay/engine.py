"""Deterministic replay from raw event log - orderbook reconstruction and time control."""

from __future__ import annotations

import json
from typing import Any, Iterator

from predexchange.ingestion.polymarket.normalize import (
    parse_book_message,
    parse_price_change_message,
)
from predexchange.orderbook.aggregator import OrderBookAggregator


def _canonical_market_id(s: str) -> str:
    """Strip 0x and lowercase so Gamma (no 0x) and WS (0x) market_ids match."""
    s = (s or "").strip()
    if s.startswith("0x"):
        s = s[2:]
    return s.lower()


def stream_raw_events(
    conn: Any,
    market_id: str | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> Iterator[tuple[dict[str, Any], int]]:
    """Yield (payload, ingest_ts) for raw_events, optionally filtered by market and time."""
    conditions = []
    params = []
    if market_id:
        conditions.append("LOWER(REPLACE(TRIM(market_id), '0x', '')) = ?")
        params.append(_canonical_market_id(market_id))
    if start_ts is not None:
        conditions.append("ingest_ts >= ?")
        params.append(start_ts)
    if end_ts is not None:
        conditions.append("ingest_ts <= ?")
        params.append(end_ts)
    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"SELECT payload, ingest_ts FROM raw_events WHERE {where} ORDER BY id ASC"
    rows = conn.execute(sql, params).fetchall()
    for payload_json, ingest_ts in rows:
        try:
            payload = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
        except (TypeError, json.JSONDecodeError):
            continue
        yield (payload, ingest_ts)


def replay_events(
    conn: Any,
    aggregator: OrderBookAggregator,
    market_id: str | None = None,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> None:
    """Replay events into the aggregator (deterministic). No timing/speed - just apply in order."""
    for payload, ingest_ts in stream_raw_events(conn, market_id=market_id, start_ts=start_ts, end_ts=end_ts):
        aggregator.on_message(payload, ingest_ts)


def replay_to_mid_series(
    conn: Any,
    market_id: str,
    asset_id: str,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> list[tuple[int, float | None]]:
    """
    Replay and return [(ingest_ts, mid_price), ...] for the given market/asset.
    Deterministic: same DB + params -> same output.
    """
    aggregator = OrderBookAggregator()
    out: list[tuple[int, float | None]] = []
    for payload, ingest_ts in stream_raw_events(conn, market_id=market_id, start_ts=start_ts, end_ts=end_ts):
        aggregator.on_message(payload, ingest_ts)
        # Engine is keyed by market_id from payload (e.g. 0x...) not request (e.g. no 0x)
        payload_market = str(payload.get("market") or payload.get("market_id") or market_id)
        eng = aggregator.get_engine(payload_market, asset_id)
        mid = eng.mid_price if eng else None
        out.append((ingest_ts, mid))
    return out


def replay_to_chart_series(
    conn: Any,
    market_id: str,
    asset_id: str,
    start_ts: int | None = None,
    end_ts: int | None = None,
    bucket_ms: int = 1000,
    depth_n: int = 5,
) -> list[dict[str, Any]]:
    """
    Replay and return bucketed series for spread/depth/OFI charts.
    Uses Python engine (use_rust=False) for depth_at_levels. Returns one row per bucket that has events.
    Each row: { ts, mid, spread, depth_bid, depth_ask, ofi }.
    OFI: buy pressure positive, sell pressure negative (bid size increase = +, ask size increase = -).
    """
    aggregator = OrderBookAggregator(use_rust=False)
    rows: list[dict[str, Any]] = []
    current_bucket_ts: int | None = None
    current_bucket_ofi: float = 0.0
    payload_market_for_engine: str | None = None

    def _emit_bucket(bucket_ts: int) -> None:
        if payload_market_for_engine is None:
            return
        eng = aggregator.get_engine(payload_market_for_engine, asset_id)
        if not eng:
            return
        mid = eng.mid_price
        spread = eng.spread
        depth_bid_list, depth_ask_list = eng.depth_at_levels(depth_n)
        depth_bid = sum(s for _, s in depth_bid_list)
        depth_ask = sum(s for _, s in depth_ask_list)
        rows.append({
            "ts": bucket_ts,
            "mid": mid,
            "spread": spread,
            "depth_bid": depth_bid,
            "depth_ask": depth_ask,
            "ofi": round(current_bucket_ofi, 6),
        })

    for payload, ingest_ts in stream_raw_events(
        conn, market_id=market_id, start_ts=start_ts, end_ts=end_ts
    ):
        event_type = payload.get("event_type")
        ts_bucket = (ingest_ts // bucket_ms) * bucket_ms
        pm = str(payload.get("market") or payload.get("market_id") or market_id)
        if pm:
            payload_market_for_engine = pm

        if current_bucket_ts is not None and ts_bucket != current_bucket_ts:
            _emit_bucket(current_bucket_ts)
            current_bucket_ofi = 0.0
        current_bucket_ts = ts_bucket

        if event_type == "book":
            snap = parse_book_message(payload)
            if snap:
                eng = aggregator._engine(snap.market_id, snap.asset_id)
                snap.ingest_ts = ingest_ts
                eng.apply_snapshot(snap)
        elif event_type == "price_change":
            for delta in parse_price_change_message(payload):
                delta.ingest_ts = ingest_ts
                eng = aggregator._engine(delta.market_id, delta.asset_id)
                side_dict = getattr(eng, "bids", {}) if delta.side == "BUY" else getattr(eng, "asks", {})
                price_key = round(delta.price, 6)
                old_size = side_dict.get(price_key, 0.0)
                eng.apply_delta(delta)
                new_size = delta.size
                delta_size = new_size - old_size
                if delta.side == "BUY":
                    current_bucket_ofi += delta_size
                else:
                    current_bucket_ofi -= delta_size
        else:
            aggregator.on_message(payload, ingest_ts)

    if current_bucket_ts is not None:
        _emit_bucket(current_bucket_ts)
    return rows


def replay_to_book_snapshots(
    conn: Any,
    market_id: str,
    asset_id: str,
    start_ts: int | None = None,
    end_ts: int | None = None,
    bucket_ms: int = 1000,
    tick_size: float = 0.01,
    ticks_around_mid: int = 50,
) -> list[dict[str, Any]]:
    """
    Replay and return per-bucket book snapshots for heatmap (price band around mid).
    Each row: { ts, mid, bids: [{ price, size }], asks: [{ price, size }] }.
    Prices are binned by tick_size; only levels in [mid - ticks_around_mid*tick, mid + ticks_around_mid*tick].
    """
    aggregator = OrderBookAggregator(use_rust=False)
    rows: list[dict[str, Any]] = []
    last_ts_bucket: int | None = None
    payload_market_for_engine: str | None = None

    def _bin_price(p: float) -> float:
        return round(round(p / tick_size) * tick_size, 6)

    def _snapshot_for_bucket(ts_bucket: int) -> None:
        if payload_market_for_engine is None:
            return
        eng = aggregator.get_engine(payload_market_for_engine, asset_id)
        if not eng or not hasattr(eng, "bids") or not hasattr(eng, "asks"):
            return
        mid = eng.mid_price
        if mid is None:
            return
        lo = max(0.0, mid - ticks_around_mid * tick_size)
        hi = min(1.0, mid + ticks_around_mid * tick_size)
        bids_dict = getattr(eng, "bids", {})
        asks_dict = getattr(eng, "asks", {})
        bids_agg: dict[float, float] = {}
        for p, s in bids_dict.items():
            if lo <= p <= hi and s > 0:
                bp = _bin_price(p)
                bids_agg[bp] = bids_agg.get(bp, 0) + s
        asks_agg: dict[float, float] = {}
        for p, s in asks_dict.items():
            if lo <= p <= hi and s > 0:
                ap = _bin_price(p)
                asks_agg[ap] = asks_agg.get(ap, 0) + s
        rows.append({
            "ts": ts_bucket,
            "mid": mid,
            "bids": [{"price": p, "size": s} for p, s in sorted(bids_agg.items(), reverse=True)],
            "asks": [{"price": p, "size": s} for p, s in sorted(asks_agg.items())],
        })

    for payload, ingest_ts in stream_raw_events(
        conn, market_id=market_id, start_ts=start_ts, end_ts=end_ts
    ):
        ts_bucket = (ingest_ts // bucket_ms) * bucket_ms
        pm = str(payload.get("market") or payload.get("market_id") or market_id)
        if pm:
            payload_market_for_engine = pm
        aggregator.on_message(payload, ingest_ts)
        if last_ts_bucket is not None and ts_bucket != last_ts_bucket:
            _snapshot_for_bucket(last_ts_bucket)
        last_ts_bucket = ts_bucket

    if last_ts_bucket is not None:
        _snapshot_for_bucket(last_ts_bucket)
    return rows
