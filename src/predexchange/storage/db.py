"""DuckDB connection and schema init."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection

SCHEMA_SQL = """
-- Sequences for auto-increment IDs
CREATE SEQUENCE IF NOT EXISTS event_seq START 1;
CREATE SEQUENCE IF NOT EXISTS snap_seq START 1;

-- Raw event log (append-only, event sourcing)
CREATE TABLE IF NOT EXISTS raw_events (
    id              BIGINT PRIMARY KEY DEFAULT nextval('event_seq'),
    venue           VARCHAR NOT NULL,
    channel         VARCHAR NOT NULL,
    event_type      VARCHAR NOT NULL,
    market_id       VARCHAR NOT NULL,
    asset_id        VARCHAR,
    exchange_ts     BIGINT,
    ingest_ts       BIGINT NOT NULL,
    payload         JSON NOT NULL
);

-- Market metadata cache
CREATE TABLE IF NOT EXISTS markets (
    market_id       VARCHAR PRIMARY KEY,
    venue           VARCHAR NOT NULL,
    title           VARCHAR,
    category        VARCHAR,
    volume_24h      DOUBLE,
    liquidity       DOUBLE,
    active          BOOLEAN,
    outcomes        JSON,
    last_updated    BIGINT
);

-- Tracked markets (currently subscribed)
CREATE TABLE IF NOT EXISTS tracked_markets (
    market_id       VARCHAR PRIMARY KEY,
    venue           VARCHAR NOT NULL,
    added_at        BIGINT NOT NULL,
    pinned          BOOLEAN DEFAULT FALSE
);

-- Derived orderbook snapshots (periodic materialized state)
CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    id              BIGINT PRIMARY KEY DEFAULT nextval('snap_seq'),
    market_id       VARCHAR NOT NULL,
    asset_id        VARCHAR NOT NULL,
    timestamp       BIGINT NOT NULL,
    best_bid        DOUBLE,
    best_ask        DOUBLE,
    mid_price       DOUBLE,
    spread          DOUBLE,
    bids_json       JSON,
    asks_json       JSON,
    imbalance       DOUBLE
);

-- Simulation runs (strategy backtest results)
CREATE TABLE IF NOT EXISTS sim_runs (
    run_id          VARCHAR PRIMARY KEY,
    strategy_name   VARCHAR NOT NULL,
    market_id       VARCHAR NOT NULL,
    params          JSON,
    final_inventory DOUBLE,
    realized_pnl    DOUBLE,
    fill_count      INTEGER,
    events_processed INTEGER,
    created_at      BIGINT
);

-- Last known mid price per (market_id, asset_id), updated when chart/series or book_heatmap is served
CREATE TABLE IF NOT EXISTS last_mid (
    market_id       VARCHAR NOT NULL,
    asset_id        VARCHAR NOT NULL,
    mid             DOUBLE NOT NULL,
    updated_at      BIGINT NOT NULL,
    PRIMARY KEY (market_id, asset_id)
);

-- Sports: latest game state from Polymarket Sports WebSocket (sport_result)
CREATE TABLE IF NOT EXISTS sports_games (
    game_id             BIGINT PRIMARY KEY,
    league_abbreviation  VARCHAR NOT NULL,
    slug                VARCHAR NOT NULL,
    home_team           VARCHAR NOT NULL,
    away_team           VARCHAR NOT NULL,
    status              VARCHAR NOT NULL,
    score               VARCHAR,
    period              VARCHAR,
    elapsed             VARCHAR,
    live                BOOLEAN NOT NULL,
    ended               BOOLEAN NOT NULL,
    turn                VARCHAR,
    finished_timestamp  VARCHAR,
    updated_at          BIGINT NOT NULL
);
"""


def get_connection(db_path: str | Path, read_only: bool = False) -> DuckDBPyConnection:
    """Return a DuckDB connection. Caller must close or use as context manager.
    Use read_only=True when another process may be writing (e.g. predex track start)
    so the API can read while ingestion holds the write lock."""
    path = Path(db_path)
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def init_schema(conn: DuckDBPyConnection) -> None:
    """Create tables and sequences if they do not exist."""
    for stmt in SCHEMA_SQL.split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except duckdb.Error as e:
                if "already exists" not in str(e).lower():
                    raise
