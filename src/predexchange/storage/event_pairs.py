"""Event pairs: curated Polymarket <-> Kalshi links for comparison."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def list_pairs(conn: DuckDBPyConnection) -> list[dict]:
    """Return all event_pairs rows as list of dicts (id, polymarket_market_id, polymarket_asset_id, kalshi_event_ticker, kalshi_market_ticker, label, created_at)."""
    rows = conn.execute(
        """
        SELECT id, polymarket_market_id, polymarket_asset_id, kalshi_event_ticker, kalshi_market_ticker, label, created_at
        FROM event_pairs
        ORDER BY id
        """
    ).fetchall()
    return [
        {
            "id": r[0],
            "polymarket_market_id": r[1],
            "polymarket_asset_id": r[2],
            "kalshi_event_ticker": r[3],
            "kalshi_market_ticker": r[4],
            "label": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


def get_pair(conn: DuckDBPyConnection, pair_id: int) -> dict | None:
    """Return one event_pair by id, or None."""
    row = conn.execute(
        "SELECT id, polymarket_market_id, polymarket_asset_id, kalshi_event_ticker, kalshi_market_ticker, label, created_at FROM event_pairs WHERE id = ?",
        [pair_id],
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "polymarket_market_id": row[1],
        "polymarket_asset_id": row[2],
        "kalshi_event_ticker": row[3],
        "kalshi_market_ticker": row[4],
        "label": row[5],
        "created_at": row[6],
    }


def add_pair(
    conn: DuckDBPyConnection,
    polymarket_market_id: str,
    kalshi_event_ticker: str,
    kalshi_market_ticker: str,
    polymarket_asset_id: str | None = None,
    label: str | None = None,
) -> int:
    """Insert a pair; returns new id. created_at set to current time (seconds)."""
    now = int(time.time())
    row = conn.execute(
        """
        INSERT INTO event_pairs (polymarket_market_id, polymarket_asset_id, kalshi_event_ticker, kalshi_market_ticker, label, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        [polymarket_market_id, polymarket_asset_id or None, kalshi_event_ticker, kalshi_market_ticker, label or None, now],
    ).fetchone()
    return int(row[0]) if row else 0
