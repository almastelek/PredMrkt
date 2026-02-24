"""FastAPI backend for web dashboard."""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from predexchange.api.schemas import (
    EventByMarketItem,
    EventsStatsResponse,
    HealthResponse,
    MarketAssetResponse,
    MarketListItem,
    MarketsListResponse,
    SimRunDetailResponse,
)
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
_config_profile: str | None = None


def _get_conn():
    settings = get_settings(_config_profile)
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
        settings = get_settings(_config_profile)
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


def _error_json(code: str, message: str, status_code: int = 404) -> JSONResponse:
    """Return consistent error JSON: { detail, code }."""
    return JSONResponse(
        status_code=status_code,
        content={"detail": message, "code": code},
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/markets", response_model=MarketsListResponse)
def markets_list(
    tracked_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> MarketsListResponse:
    """List markets with optional limit/offset."""
    conn = _get_conn()
    try:
        all_markets = storage_list_markets(conn, tracked_only=tracked_only)
        total = len(all_markets)
        markets = all_markets[offset : offset + limit]
        return MarketsListResponse(markets=markets, total=total)
    finally:
        conn.close()


@app.get("/events/stats", response_model=EventsStatsResponse)
def events_stats() -> EventsStatsResponse:
    conn = _get_conn()
    try:
        data = log_stats(conn)
        return EventsStatsResponse(
            total_events=data["total_events"],
            min_ingest_ts=data.get("min_ingest_ts"),
            max_ingest_ts=data.get("max_ingest_ts"),
            by_market=data.get("by_market", []),
        )
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


def _market_meta_from_db(conn, canonical: str, normalized: str, market_id_param: str) -> tuple[str | None, str | None]:
    """Return (title, category) from markets table for this condition_id. Empty string -> None."""
    row = conn.execute(
        """SELECT title, category FROM markets
           WHERE LOWER(REPLACE(TRIM(market_id), '0x', '')) = ?
              OR TRIM(market_id) = ?
              OR TRIM(market_id) = ?
           LIMIT 1""",
        [canonical, normalized, market_id_param],
    ).fetchone()
    if not row:
        return (None, None)
    title = (row[0] or "").strip() or None
    category = (row[1] or "").strip() or None
    return (title, category)


@app.get("/markets/{market_id}/asset")
def market_asset(market_id: str):
    """Return asset_id and optional title/category for an event (condition). 404 if unknown."""
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
        asset_id = row[0] if row and row[0] else None
        if not asset_id:
            asset_id = _asset_id_from_markets(conn, canonical, normalized, market_id)
        if not asset_id:
            return JSONResponse(status_code=404, content={"detail": "no_events", "message": "No ingested events for this market"})
        title, category = _market_meta_from_db(conn, canonical, normalized, market_id)
        out: dict[str, Any] = {"market_id": market_id, "asset_id": asset_id}
        if title is not None:
            out["title"] = title
        if category is not None:
            out["category"] = category
        return out
    finally:
        conn.close()


@app.get("/events/by_market")
def events_by_market(
    limit: int = Query(40, ge=1, le=100),
    sparkline_buckets: int = Query(12, ge=0, le=48),
) -> list[dict[str, Any]]:
    """Event counts per event (condition). Joins markets for title/category. Optional sparkline = counts per 5-min bucket."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            WITH counts AS (
                SELECT market_id, COUNT(*) AS cnt
                FROM raw_events
                GROUP BY market_id
                ORDER BY cnt DESC
                LIMIT ?
            )
            SELECT c.market_id, c.cnt, m.title, m.category
            FROM counts c
            LEFT JOIN markets m ON
                LOWER(REPLACE(TRIM(m.market_id), '0x', '')) = LOWER(REPLACE(TRIM(c.market_id), '0x', ''))
            """,
            [limit],
        ).fetchall()
        out = [
            {
                "market_id": r[0],
                "event_count": r[1],
                "title": (r[2] or "").strip() or None,
                "category": (r[3] or "").strip() or None,
            }
            for r in rows
        ]
        if sparkline_buckets <= 0:
            return out
        # Sparkline: last N buckets of 5 min each (ingest_ts in ms)
        now_ms = int(time.time() * 1000)
        bucket_ms = 5 * 60 * 1000
        start_ms = now_ms - sparkline_buckets * bucket_ms
        market_ids = [r["market_id"] for r in out]
        if not market_ids:
            return out
        placeholders = ",".join("?" for _ in market_ids)
        bucket_rows = conn.execute(
            f"""
            SELECT market_id, FLOOR((ingest_ts - ?) / ?)::INTEGER AS bucket, COUNT(*) AS cnt
            FROM raw_events
            WHERE market_id IN ({placeholders}) AND ingest_ts >= ?
            GROUP BY market_id, bucket
            """,
            [start_ms, bucket_ms] + market_ids + [start_ms],
        ).fetchall()
        by_market: dict[str, list[int]] = {mid: [0] * sparkline_buckets for mid in market_ids}
        for mid, bucket_idx, cnt in bucket_rows:
            idx = int(bucket_idx) if bucket_idx is not None else -1
            if 0 <= idx < sparkline_buckets:
                by_market[mid][idx] = cnt
        for item in out:
            item["sparkline"] = by_market.get(item["market_id"], [0] * sparkline_buckets)
        return out
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
