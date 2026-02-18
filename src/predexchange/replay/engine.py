"""Deterministic replay from raw event log - orderbook reconstruction and time control."""

from __future__ import annotations

import json
from typing import Any, Iterator

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
