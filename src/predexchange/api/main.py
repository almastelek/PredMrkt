"""FastAPI backend for web dashboard."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from predexchange.config import get_settings
from predexchange.replay.engine import (
    replay_to_book_snapshots,
    replay_to_chart_series,
    replay_to_mid_series,
)
from predexchange.storage.db import get_connection
from predexchange.storage.event_log import log_stats, normalize_condition_id
from predexchange.storage.markets import list_markets as storage_list_markets
from predexchange.simulation.runner import get_run_result

# Set by run_api() so lifespan can start ingestion in the same process (avoids DuckDB cross-process lock).
_run_with_ingestion = False


def _get_conn():
    settings = get_settings()
    # With ingestion in-process, DuckDB requires same config for all connections to the same file; use read_only=False to match ingestion.
    read_only = not _run_with_ingestion
    conn = get_connection(settings.db_path, read_only=read_only)
    return conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    ingestion_task = None
    ingestion_stop = None
    ingestion_manager = None

    if _run_with_ingestion:
        settings = get_settings()
        from predexchange.ingestion.manager import IngestionManager

        ingestion_manager = IngestionManager(
            db_path=settings.db_path,
            ws_url=settings.clob_ws_url,
            event_batch_size=settings.event_batch_size,
            reconnect_base_delay_sec=settings.reconnect_base_delay_sec,
            reconnect_max_delay_sec=settings.reconnect_max_delay_sec,
            reconnect_max_retries=settings.reconnect_max_retries,
        )
        ingestion_stop = asyncio.Event()
        ingestion_task = asyncio.create_task(ingestion_manager.run(stop_event=ingestion_stop))

    yield

    if ingestion_task is not None and ingestion_stop is not None and ingestion_manager is not None:
        ingestion_stop.set()
        await ingestion_task
        ingestion_manager.close()


app = FastAPI(title="PredExchange API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/markets")
def markets_list(
    tracked_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List markets with optional limit/offset. Returns { markets, total }."""
    conn = _get_conn()
    try:
        all_markets = storage_list_markets(conn, tracked_only=tracked_only)
        total = len(all_markets)
        markets = all_markets[offset : offset + limit]
        return {"markets": markets, "total": total}
    finally:
        conn.close()


@app.get("/events/stats")
def events_stats() -> dict[str, Any]:
    conn = _get_conn()
    try:
        return log_stats(conn)
    finally:
        conn.close()


@app.get("/sim/runs")
def sim_runs_list() -> list[str]:
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT run_id FROM sim_runs ORDER BY created_at DESC LIMIT 50").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


@app.get("/markets/{market_id}/timeseries")
def market_timeseries(
    market_id: str,
    asset_id: str = Query(..., description="Asset (token) ID for this market"),
    start_ts: int | None = Query(None),
    end_ts: int | None = Query(None),
    max_points: int = Query(500, ge=1, le=2000),
) -> dict[str, Any]:
    """Replay and return mid-price time series for a market. Same data as replay engine."""
    market_id = normalize_condition_id(market_id)
    conn = _get_conn()
    try:
        series = replay_to_mid_series(conn, market_id, asset_id, start_ts=start_ts, end_ts=end_ts)
        if len(series) > max_points:
            step = len(series) // max_points
            series = series[:: max(1, step)][:max_points]
        return {"market_id": market_id, "asset_id": asset_id, "series": [{"t": t, "mid": m} for t, m in series]}
    finally:
        conn.close()


def _chart_window_ms(start_ts: int | None, end_ts: int | None, default_minutes: int = 30) -> tuple[int | None, int | None]:
    """If both None, return (now - default_minutes, now) in ms."""
    if start_ts is not None and end_ts is not None:
        return start_ts, end_ts
    import time
    now_ms = int(time.time() * 1000)
    if start_ts is None and end_ts is None:
        return now_ms - default_minutes * 60 * 1000, now_ms
    if start_ts is None:
        return end_ts - default_minutes * 60 * 1000, end_ts
    return start_ts, now_ms


@app.get("/markets/{market_id}/chart/series")
def market_chart_series(
    market_id: str,
    asset_id: str = Query(..., description="Asset (token) ID for this market"),
    start_ts: int | None = Query(None),
    end_ts: int | None = Query(None),
    resolution: int = Query(1000, ge=250, le=60000, description="Bucket size in ms (1s default)"),
    depth_n: int = Query(5, ge=1, le=20, description="Top N levels for depth"),
) -> dict[str, Any]:
    """Bucketed series for spread/depth/OFI charts. Window-based; default last 30m if no start/end."""
    market_id = normalize_condition_id(market_id)
    start_ts, end_ts = _chart_window_ms(start_ts, end_ts)
    conn = _get_conn()
    try:
        series = replay_to_chart_series(
            conn,
            market_id,
            asset_id,
            start_ts=start_ts,
            end_ts=end_ts,
            bucket_ms=resolution,
            depth_n=depth_n,
        )
        return {"market_id": market_id, "asset_id": asset_id, "series": series}
    finally:
        conn.close()


@app.get("/markets/{market_id}/chart/book_heatmap")
def market_chart_book_heatmap(
    market_id: str,
    asset_id: str = Query(..., description="Asset (token) ID for this market"),
    start_ts: int | None = Query(None),
    end_ts: int | None = Query(None),
    resolution: int = Query(1000, ge=500, le=10000),
    tick_size: float = Query(0.01, ge=0.001, le=0.1),
    ticks_around_mid: int = Query(50, ge=10, le=200),
) -> dict[str, Any]:
    """Book snapshots per bucket for depth heatmap (price band around mid). Default last 30m."""
    market_id = normalize_condition_id(market_id)
    start_ts, end_ts = _chart_window_ms(start_ts, end_ts)
    conn = _get_conn()
    try:
        snapshots = replay_to_book_snapshots(
            conn,
            market_id,
            asset_id,
            start_ts=start_ts,
            end_ts=end_ts,
            bucket_ms=resolution,
            tick_size=tick_size,
            ticks_around_mid=ticks_around_mid,
        )
        return {"market_id": market_id, "asset_id": asset_id, "snapshots": snapshots}
    finally:
        conn.close()


def _canonical_market_id(s: str) -> str:
    """Strip 0x and lowercase so Gamma (no 0x) and WS (0x) market_ids match."""
    s = (s or "").strip()
    if s.startswith("0x"):
        s = s[2:]
    return s.lower()


def _asset_id_from_markets(conn, canonical: str, normalized: str, market_id_param: str) -> str | None:
    """Fallback: get first outcome token_id from markets table for this condition_id."""
    row = conn.execute(
        """SELECT outcomes FROM markets
           WHERE LOWER(REPLACE(TRIM(market_id), '0x', '')) = ?
              OR TRIM(market_id) = ?
              OR TRIM(market_id) = ?
           LIMIT 1""",
        [canonical, normalized, market_id_param],
    ).fetchone()
    if not row or not row[0]:
        return None
    try:
        outcomes = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        for o in (outcomes or []):
            if isinstance(o, dict) and o.get("token_id"):
                return str(o["token_id"])
    except (TypeError, ValueError):
        pass
    return None


@app.get("/markets/{market_id}/asset")
def market_asset(market_id: str):
    """Return first asset_id for a market (from raw_events or markets.outcomes). 404 if unknown."""
    market_id = (market_id or "").strip()
    if not market_id:
        return JSONResponse(status_code=404, content={"detail": "no_events", "message": "No ingested events for this market"})
    canonical = _canonical_market_id(market_id)
    normalized = normalize_condition_id(market_id)  # 0x + lower if hex
    conn = _get_conn()
    try:
        # Prefer asset_id from raw_events (proves we have ingested data for this market)
        row = conn.execute(
            """SELECT DISTINCT asset_id FROM raw_events
               WHERE asset_id IS NOT NULL AND TRIM(asset_id) != ''
                 AND (LOWER(REPLACE(TRIM(market_id), '0x', '')) = ?
                      OR TRIM(market_id) = ?
                      OR TRIM(market_id) = ?)
               LIMIT 1""",
            [canonical, normalized, market_id],
        ).fetchone()
        if row and row[0]:
            return {"market_id": market_id, "asset_id": row[0]}
        # Fallback: discovered market with outcomes (token_id) but no events with asset_id yet
        asset_id = _asset_id_from_markets(conn, canonical, normalized, market_id)
        if asset_id:
            return {"market_id": market_id, "asset_id": asset_id}
        return JSONResponse(status_code=404, content={"detail": "no_events", "message": "No ingested events for this market"})
    finally:
        conn.close()


@app.get("/events/by_market")
def events_by_market(limit: int = Query(30, ge=1, le=100)) -> list[dict[str, Any]]:
    """Event counts per market (for bar charts). Joins markets table for title when available."""
    conn = _get_conn()
    try:
        # Normalize condition_id for join: strip 0x and lowercase so Gamma (sometimes no 0x) matches WS (0x)
        rows = conn.execute(
            """
            WITH counts AS (
                SELECT market_id, COUNT(*) AS cnt
                FROM raw_events
                GROUP BY market_id
                ORDER BY cnt DESC
                LIMIT ?
            )
            SELECT c.market_id, c.cnt, m.title
            FROM counts c
            LEFT JOIN markets m ON
                LOWER(REPLACE(TRIM(m.market_id), '0x', '')) = LOWER(REPLACE(TRIM(c.market_id), '0x', ''))
            """,
            [limit],
        ).fetchall()
        return [
            {"market_id": r[0], "event_count": r[1], "title": (r[2] or "").strip() or None}
            for r in rows
        ]
    finally:
        conn.close()


@app.get("/sim/runs/{run_id}")
def sim_run_detail(run_id: str) -> dict[str, Any] | None:
    conn = _get_conn()
    try:
        r = get_run_result(conn, run_id)
        if not r:
            return None
        return {
            "run_id": r.run_id,
            "strategy_name": r.strategy_name,
            "market_id": r.market_id,
            "events_processed": r.events_processed,
            "fill_count": r.fill_count,
            "realized_pnl": r.realized_pnl,
            "final_inventory": r.final_inventory,
            "params": r.params,
        }
    finally:
        conn.close()


def run_api(host: str = "127.0.0.1", port: int = 8000, with_ingestion: bool = False) -> None:
    global _run_with_ingestion
    _run_with_ingestion = with_ingestion
    import uvicorn
    uvicorn.run("predexchange.api.main:app", host=host, port=port, reload=False)
