"""FastAPI backend for web dashboard."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from predexchange.config import get_settings
from predexchange.storage.db import get_connection, init_schema
from predexchange.storage.event_log import log_stats
from predexchange.storage.markets import list_markets as storage_list_markets
from predexchange.simulation.runner import get_run_result


def _get_conn():
    settings = get_settings()
    conn = get_connection(settings.db_path)
    init_schema(conn)
    return conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # No persistent connection to close (we open per-request)


app = FastAPI(title="PredExchange API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/markets")
def markets_list(tracked_only: bool = False) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        return storage_list_markets(conn, tracked_only=tracked_only)
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


def run_api(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn
    uvicorn.run("predexchange.api.main:app", host=host, port=port, reload=False)
