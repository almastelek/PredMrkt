"""Raw event append and query - event sourcing log."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def normalize_condition_id(s: str) -> str:
    """Canonicalize condition_id / market for matching (Gamma and CLOB WS use 0x + 64 hex)."""
    s = (s or "").strip()
    if not s:
        return s
    if s.startswith("0x"):
        return "0x" + s[2:].lower()
    return s.lower() if len(s) == 64 and all(c in "0123456789abcdefABCDEF" for c in s) else s


def _extract_event_meta(payload: dict[str, Any]) -> tuple[str, str, str | None, int | None]:
    """Extract venue-level event_type, market_id, asset_id, exchange_ts from Polymarket-style message."""
    event_type = str(payload.get("event_type", "unknown"))
    market_id = normalize_condition_id(str(payload.get("market") or payload.get("market_id") or ""))
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


def prepare_polymarket_rows(
    payload: dict[str, Any],
    ingest_ts: int,
    venue: str = "polymarket",
    channel: str = "market",
) -> list[tuple[str, str, str, str, str | None, int | None, int, str]]:
    """
    Build raw_events row(s) from a Polymarket WS message.
    For 'price_change', returns one row per price_changes entry (asset_id is inside each entry).
    For other messages, returns a single row (same as prepare_polymarket_row).
    """
    event_type = str(payload.get("event_type", "unknown"))
    market_id = normalize_condition_id(str(payload.get("market") or payload.get("market_id") or ""))
    ts = payload.get("timestamp")
    try:
        exchange_ts = int(ts) if ts is not None else None
    except (TypeError, ValueError):
        exchange_ts = None
    if isinstance(exchange_ts, str):
        try:
            exchange_ts = int(exchange_ts)
        except (TypeError, ValueError):
            exchange_ts = None
    payload_json = json.dumps(payload)

    if event_type == "price_change":
        changes = payload.get("price_changes") or []
        rows = []
        for pc in changes:
            if not isinstance(pc, dict):
                continue
            asset_id = pc.get("asset_id")
            if asset_id is not None:
                asset_id = str(asset_id).strip() or None
            if not asset_id:
                continue
            rows.append((venue, channel, event_type, market_id, asset_id, exchange_ts, ingest_ts, payload_json))
        return rows if rows else [prepare_polymarket_row(payload, ingest_ts, venue, channel)]
    return [prepare_polymarket_row(payload, ingest_ts, venue, channel)]
