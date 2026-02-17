"""Raw event append and query - event sourcing log."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def _extract_event_meta(payload: dict[str, Any]) -> tuple[str, str, str | None, int | None]:
    """Extract venue-level event_type, market_id, asset_id, exchange_ts from Polymarket-style message."""
    event_type = str(payload.get("event_type", "unknown"))
    market_id = str(payload.get("market") or payload.get("market_id") or "")
    asset_id = payload.get("asset_id")
    if asset_id is not None:
        asset_id = str(asset_id)
    ts = payload.get("timestamp")
    if ts is not None:
        try:
            exchange_ts = int(ts)
        except (TypeError, ValueError):
            exchange_ts = None
    else:
        exchange_ts = None
    return event_type, market_id, asset_id, exchange_ts


def append_raw_event(
    conn: DuckDBPyConnection,
    venue: str,
    channel: str,
    event_type: str,
    market_id: str,
    asset_id: str | None,
    exchange_ts: int | None,
    ingest_ts: int,
    payload: dict[str, Any],
) -> None:
    """Append a single raw event. Prefer append_raw_events_batch for throughput."""
    payload_json = json.dumps(payload)
    conn.execute(
        """
        INSERT INTO raw_events (venue, channel, event_type, market_id, asset_id, exchange_ts, ingest_ts, payload)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [venue, channel, event_type, market_id, asset_id, exchange_ts, ingest_ts, payload_json],
    )


def append_raw_events_batch(
    conn: DuckDBPyConnection,
    rows: list[tuple[str, str, str, str, str | None, int | None, int, str]],
) -> None:
    """Append multiple raw events. Each row: (venue, channel, event_type, market_id, asset_id, exchange_ts, ingest_ts, payload_json)."""
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO raw_events (venue, channel, event_type, market_id, asset_id, exchange_ts, ingest_ts, payload)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def log_stats(conn: DuckDBPyConnection) -> dict[str, Any]:
    """Return event log statistics: total count, min/max ingest_ts, count by market_id."""
    total = conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
    range_row = conn.execute(
        "SELECT MIN(ingest_ts), MAX(ingest_ts) FROM raw_events"
    ).fetchone()
    min_ts, max_ts = range_row[0], range_row[1]
    by_market = conn.execute(
        "SELECT market_id, COUNT(*) AS cnt FROM raw_events GROUP BY market_id ORDER BY cnt DESC LIMIT 20"
    ).fetchall()
    return {
        "total_events": total,
        "min_ingest_ts": min_ts,
        "max_ingest_ts": max_ts,
        "by_market": [{"market_id": r[0], "count": r[1]} for r in by_market],
    }


def prepare_polymarket_row(
    payload: dict[str, Any],
    ingest_ts: int,
    venue: str = "polymarket",
    channel: str = "market",
) -> tuple[str, str, str, str, str | None, int | None, int, str]:
    """Build a raw_events row from a Polymarket WS message."""
    event_type, market_id, asset_id, exchange_ts = _extract_event_meta(payload)
    payload_json = json.dumps(payload)
    return (venue, channel, event_type, market_id, asset_id, exchange_ts, ingest_ts, payload_json)
