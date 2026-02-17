"""Deterministic replay from raw event log - orderbook reconstruction and time control."""

from __future__ import annotations

import json
from typing import Any, Iterator

from predexchange.orderbook.aggregator import OrderBookAggregator


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
        conditions.append("market_id = ?")
        params.append(market_id)
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
        eng = aggregator.get_engine(market_id, asset_id)
        mid = eng.mid_price if eng else None
        out.append((ingest_ts, mid))
    return out
