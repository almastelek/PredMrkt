"""Market and tracked_markets persistence."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from predexchange.models import Market

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def upsert_market(conn: DuckDBPyConnection, market: Market) -> None:
    """Insert or replace a market in the markets table."""
    outcomes_json = json.dumps([o.model_dump() for o in market.outcomes])
    conn.execute(
        """
        INSERT INTO markets (market_id, venue, title, category, volume_24h, liquidity, active, outcomes, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (market_id) DO UPDATE SET
            venue = excluded.venue,
            title = excluded.title,
            category = excluded.category,
            volume_24h = excluded.volume_24h,
            liquidity = excluded.liquidity,
            active = excluded.active,
            outcomes = excluded.outcomes,
            last_updated = excluded.last_updated
        """,
        [
            market.market_id,
            market.venue,
            market.title or market.question,
            market.category,
            market.volume_24h,
            market.liquidity,
            market.active,
            outcomes_json,
            market.last_updated or int(time.time() * 1000),
        ],
    )


def upsert_markets(conn: DuckDBPyConnection, markets: list[Market]) -> None:
    """Upsert multiple markets."""
    for m in markets:
        upsert_market(conn, m)


def set_tracked_markets(conn: DuckDBPyConnection, market_ids: list[str], venue: str = "polymarket") -> None:
    """Replace tracked_markets with the given market IDs. Pinned ones are preserved if present."""
    now_ms = int(time.time() * 1000)
    # Get current pinned
    pinned = set()
    try:
        rows = conn.execute(
            "SELECT market_id FROM tracked_markets WHERE pinned = true"
        ).fetchall()
        pinned = {r[0] for r in rows}
    except Exception:
        pass
    conn.execute("DELETE FROM tracked_markets")
    for mid in market_ids:
        conn.execute(
            "INSERT INTO tracked_markets (market_id, venue, added_at, pinned) VALUES (?, ?, ?, ?)",
            [mid, venue, now_ms, mid in pinned],
        )


def list_markets(conn: DuckDBPyConnection, tracked_only: bool = False) -> list[dict]:
    """List markets (or tracked only) as list of dicts."""
    if tracked_only:
        rows = conn.execute(
            """
            SELECT m.market_id, m.venue, m.title, m.category, m.volume_24h, m.liquidity, m.active, m.outcomes, m.last_updated
            FROM markets m
            JOIN tracked_markets t ON m.market_id = t.market_id
            ORDER BY t.added_at
            """
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT market_id, venue, title, category, volume_24h, liquidity, active, outcomes, last_updated FROM markets ORDER BY volume_24h DESC"
        ).fetchall()
    columns = ["market_id", "venue", "title", "category", "volume_24h", "liquidity", "active", "outcomes", "last_updated"]
    return [dict(zip(columns, r)) for r in rows]


def get_tracked_market_ids(conn: DuckDBPyConnection) -> list[str]:
    """Return list of tracked market IDs in order."""
    rows = conn.execute("SELECT market_id FROM tracked_markets ORDER BY added_at").fetchall()
    return [r[0] for r in rows]
