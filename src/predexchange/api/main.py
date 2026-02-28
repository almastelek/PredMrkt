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
    ErrorResponse,
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
from predexchange.storage.db import get_connection, init_schema
from predexchange.storage.event_log import log_stats, normalize_condition_id
from predexchange.storage.markets import list_markets as storage_list_markets
from predexchange.storage.sports import list_sports_games
from predexchange.simulation.runner import get_run_result

# Set by run_api() so lifespan can start ingestion/sports in the same process.
_run_with_ingestion = False
_run_with_sports = False
_config_profile: str | None = None


def _get_conn():
    settings = get_settings(_config_profile)
    # With ingestion in-process, DuckDB requires same config for all connections to the same file; use read_only=False to match ingestion.
    read_only = not (_run_with_ingestion or _run_with_sports)
    conn = get_connection(settings.db_path, read_only=read_only)
    return conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure schema (including last_mid) exists
    settings = get_settings(_config_profile)
    conn = get_connection(settings.db_path, read_only=False)
    try:
        init_schema(conn)
    finally:
        conn.close()

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

    sports_task = None
    sports_stop = None
    if _run_with_sports:
        from predexchange.ingestion.polymarket.sports_ws import run_sports_ws
        from predexchange.storage.sports import upsert_sport_result

        settings = get_settings(_config_profile)
        db_path = settings.db_path

        def _on_sport_result(payload: dict[str, Any], ingest_ts: int) -> None:
            c = get_connection(db_path, read_only=False)
            try:
                init_schema(c)
                upsert_sport_result(c, payload, ingest_ts)
            finally:
                c.close()

        sports_stop = asyncio.Event()
        sports_task = asyncio.create_task(run_sports_ws(_on_sport_result, stop_event=sports_stop))

    yield

    if ingestion_task is not None and ingestion_stop is not None and ingestion_manager is not None:
        ingestion_stop.set()
        await ingestion_task
        ingestion_manager.close()
    if sports_task is not None and sports_stop is not None:
        sports_stop.set()
        await sports_task


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


def _upsert_last_mid(conn: Any, market_id: str, asset_id: str, mid: float) -> None:
    """Write last known mid for this (market_id, asset_id). Swallow errors to avoid 500s under concurrent load."""
    if mid is None or not (0 <= mid <= 1):
        return
    try:
        now_ms = int(time.time() * 1000)
        conn.execute(
            """INSERT INTO last_mid (market_id, asset_id, mid, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT (market_id, asset_id) DO UPDATE SET mid = excluded.mid, updated_at = excluded.updated_at""",
            [market_id, asset_id, mid, now_ms],
        )
    except Exception:
        pass  # avoid 500 when DuckDB conflicts under concurrent chart/series + book_heatmap


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
        if series:
            last = series[-1]
            if last.get("mid") is not None:
                _upsert_last_mid(conn, market_id, asset_id, float(last["mid"]))
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
        if snapshots:
            last = snapshots[-1]
            if last.get("mid") is not None:
                _upsert_last_mid(conn, market_id, asset_id, float(last["mid"]))
        return {"market_id": market_id, "asset_id": asset_id, "snapshots": snapshots}
    finally:
        conn.close()


def _canonical_market_id(s: str) -> str:
    """Strip 0x and lowercase so Gamma (no 0x) and WS (0x) market_ids match."""
    s = (s or "").strip()
    if s.startswith("0x"):
        s = s[2:]
    return s.lower()


def _canonical_asset_id_from_markets(conn, canonical: str, normalized: str, market_id_param: str) -> str | None:
    """
    Get the canonical outcome token_id for this condition_id from the markets table.
    Prefer the 'Yes' outcome so we always show the same side (probability p, not 1-p).
    If no 'Yes', return first outcome by token_id for deterministic ordering.
    """
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
        if not outcomes or not isinstance(outcomes, list):
            return None
        # Prefer outcome named "Yes" (binary markets: Yes = p, No = 1-p; we want p)
        yes_token: str | None = None
        all_tokens: list[str] = []
        for o in outcomes:
            if not isinstance(o, dict) or not o.get("token_id"):
                continue
            tid = str(o["token_id"])
            all_tokens.append(tid)
            name = (o.get("name") or "").strip().lower()
            if name == "yes":
                yes_token = tid
        if yes_token:
            return yes_token
        # No "Yes" found; return deterministic first (e.g. multi-outcome market)
        if all_tokens:
            return min(all_tokens)
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


@app.get(
    "/markets/{market_id}/asset",
    response_model=MarketAssetResponse,
    responses={404: {"description": "No events for this market", "model": ErrorResponse}},
)
def market_asset(market_id: str):
    """Return asset_id and optional title/category for an event (condition). 404 if unknown."""
    market_id = (market_id or "").strip()
    if not market_id:
        return _error_json("no_events", "No ingested events for this market")
    canonical = _canonical_market_id(market_id)
    normalized = normalize_condition_id(market_id)  # 0x + lower if hex
    conn = _get_conn()
    try:
        # Get all distinct asset_ids so we can pick one deterministically (avoid Yes/No flip)
        rows = conn.execute(
            """SELECT DISTINCT asset_id FROM raw_events
               WHERE asset_id IS NOT NULL AND TRIM(asset_id) != ''
                 AND (LOWER(REPLACE(TRIM(market_id), '0x', '')) = ?
                      OR TRIM(market_id) = ?
                      OR TRIM(market_id) = ?)
               ORDER BY asset_id""",
            [canonical, normalized, market_id],
        ).fetchall()
        raw_asset_ids = [r[0] for r in rows if r and r[0]]
        canonical_asset = _canonical_asset_id_from_markets(conn, canonical, normalized, market_id)
        if canonical_asset and canonical_asset in raw_asset_ids:
            asset_id = canonical_asset
        elif raw_asset_ids:
            asset_id = min(raw_asset_ids)
        else:
            asset_id = canonical_asset
        if not asset_id:
            return _error_json("no_events", "No ingested events for this market")
        title, category = _market_meta_from_db(conn, canonical, normalized, market_id)
        return MarketAssetResponse(market_id=market_id, asset_id=asset_id, title=title, category=category)
    finally:
        conn.close()


@app.get("/events/by_market", response_model=list[EventByMarketItem])
def events_by_market(
    limit: int = Query(40, ge=1, le=100),
    sparkline_buckets: int = Query(12, ge=0, le=48),
    category: str | None = Query(None, description="Filter by market category (e.g. Politics, Sports)"),
) -> list[EventByMarketItem]:
    """Event counts per event (condition). Joins markets for title/category. Optional category filter and sparkline."""
    conn = _get_conn()
    try:
        # Fetch more when filtering by category so we have enough after filter
        fetch_limit = limit * 3 if category else limit
        rows = conn.execute(
            """
            WITH counts AS (
                SELECT market_id, COUNT(*) AS cnt
                FROM raw_events
                GROUP BY market_id
                ORDER BY cnt DESC
                LIMIT ?
            ),
            joined AS (
                SELECT c.market_id, c.cnt, m.title, m.category
                FROM counts c
                LEFT JOIN markets m ON
                    LOWER(REPLACE(TRIM(m.market_id), '0x', '')) = LOWER(REPLACE(TRIM(c.market_id), '0x', ''))
            )
            SELECT market_id, cnt, title, category FROM joined
            WHERE (? IS NULL OR TRIM(COALESCE(category, '')) = ?)
            LIMIT ?
            """,
            [fetch_limit, category, (category or "").strip(), limit],
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
        # Last known mid (probability) per market (one row per market_id, latest updated_at)
        try:
            mid_rows = conn.execute(
                """
                SELECT l.market_id, l.mid FROM last_mid l
                JOIN (SELECT market_id, MAX(updated_at) AS updated_at FROM last_mid GROUP BY market_id) t
                ON l.market_id = t.market_id AND l.updated_at = t.updated_at
                """
            ).fetchall()
            mid_by_normalized = {normalize_condition_id(r[0]): r[1] for r in mid_rows}
            for d in out:
                d["last_mid"] = mid_by_normalized.get(normalize_condition_id(d["market_id"]))
        except Exception:
            for d in out:
                d["last_mid"] = None
        if sparkline_buckets <= 0:
            return [EventByMarketItem(**d) for d in out]
        now_ms = int(time.time() * 1000)
        bucket_ms = 5 * 60 * 1000
        start_ms = now_ms - sparkline_buckets * bucket_ms
        market_ids = [d["market_id"] for d in out]
        if not market_ids:
            return [EventByMarketItem(**d) for d in out]
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
        for d in out:
            d["sparkline"] = by_market.get(d["market_id"], [0] * sparkline_buckets)
        return [EventByMarketItem(**d) for d in out]
    finally:
        conn.close()


@app.get("/sports/games")
def sports_games_list(
    league: str | None = Query(None, description="Filter by league (e.g. nfl, nhl, nba, mlb, cfb, cs2)"),
    status: str | None = Query(None, description="Filter by status (e.g. InProgress, Scheduled, Final)"),
    limit: int = Query(200, ge=1, le=500),
) -> list[dict[str, Any]]:
    """List sports games from Polymarket Sports WebSocket. Live games first when no status filter."""
    conn = _get_conn()
    try:
        return list_sports_games(conn, league=league, status=status, live_first=True, limit=limit)
    finally:
        conn.close()


@app.get(
    "/sim/runs/{run_id}",
    response_model=SimRunDetailResponse,
    responses={404: {"description": "Sim run not found", "model": ErrorResponse}},
)
def sim_run_detail(run_id: str):
    """Simulation run detail. 404 if run_id not found."""
    conn = _get_conn()
    try:
        r = get_run_result(conn, run_id)
        if not r:
            return _error_json("not_found", f"Sim run not found: {run_id}")
        return SimRunDetailResponse(
            run_id=r.run_id,
            strategy_name=r.strategy_name,
            market_id=r.market_id,
            events_processed=r.events_processed,
            fill_count=r.fill_count,
            realized_pnl=r.realized_pnl,
            final_inventory=r.final_inventory,
            params=r.params or {},
        )
    finally:
        conn.close()


def run_api(
    host: str = "127.0.0.1",
    port: int = 8000,
    with_ingestion: bool = False,
    with_sports: bool = False,
    profile: str | None = None,
) -> None:
    global _run_with_ingestion, _run_with_sports, _config_profile
    _run_with_ingestion = with_ingestion
    _run_with_sports = with_sports or with_ingestion
    _config_profile = profile
    import uvicorn
    uvicorn.run("predexchange.api.main:app", host=host, port=port, reload=False)
