"""Persist orderbook snapshots (derived metrics) to DuckDB."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def append_snapshot(
    conn: DuckDBPyConnection,
    market_id: str,
    asset_id: str,
    timestamp: int,
    best_bid: float | None,
    best_ask: float | None,
    mid_price: float | None,
    spread: float | None,
    bids_json: str,
    asks_json: str,
    imbalance: float | None,
) -> None:
    """Append one orderbook_snapshots row."""
    conn.execute(
        """
        INSERT INTO orderbook_snapshots (market_id, asset_id, timestamp, best_bid, best_ask, mid_price, spread, bids_json, asks_json, imbalance)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            market_id,
            asset_id,
            timestamp,
            best_bid,
            best_ask,
            mid_price,
            spread,
            bids_json,
            asks_json,
            imbalance,
        ],
    )


def snapshot_from_engine(engine: Any, ingest_ts: int) -> None:
    """Helper: take current engine state and append to conn. Requires engine to have market_id, asset_id, and metrics."""
    # Used by caller who has conn and engine
    pass
