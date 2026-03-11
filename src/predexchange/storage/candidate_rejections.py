"""Rejected candidate pairs: admin-dismissed suggestions so we don't resuggest."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def add_rejection(
    conn: DuckDBPyConnection,
    polymarket_market_id: str,
    kalshi_market_ticker: str,
) -> None:
    """Record a rejected candidate pair. Idempotent (upsert)."""
    now = int(time.time())
    conn.execute(
        """
        INSERT INTO candidate_rejections (polymarket_market_id, kalshi_market_ticker, rejected_at)
        VALUES (?, ?, ?)
        ON CONFLICT (polymarket_market_id, kalshi_market_ticker) DO UPDATE SET rejected_at = excluded.rejected_at
        """,
        [polymarket_market_id.strip(), kalshi_market_ticker.strip(), now],
    )


def get_rejected_set(conn: DuckDBPyConnection) -> set[tuple[str, str]]:
    """Return set of (polymarket_market_id, kalshi_market_ticker) that have been rejected."""
    try:
        rows = conn.execute(
            "SELECT polymarket_market_id, kalshi_market_ticker FROM candidate_rejections"
        ).fetchall()
        return {(r[0], r[1]) for r in rows}
    except Exception:
        return set()
