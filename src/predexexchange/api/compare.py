"""Event compare API: list and detail for Polymarket <-> Kalshi pairs."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from predexexchange.api.schemas import CompareDetailResponse, CompareListResponse, ComparePairItem
from predexexchange.config import get_settings
from predexexchange.ingestion.kalshi.client import KalshiClient
from predexexchange.storage.db import get_connection
from predexexchange.storage.event_pairs import get_pair as get_event_pair, list_pairs as list_event_pairs

router = APIRouter()


def _get_conn():
    settings = get_settings()
    conn = get_connection(settings.db_path, read_only=True)
    return conn


def _polymarket_title(conn, market_id: str) -> str | None:
    row = conn.execute("SELECT title FROM markets WHERE market_id = ?", [market_id]).fetchone()
    return row[0] if row else None


@router.get("/compare", response_model=CompareListResponse)
def events_compare_list() -> CompareListResponse:
    """List all curated event pairs (Polymarket <-> Kalshi). Enriched with titles from DB and Kalshi API."""
    conn = _get_conn()
    try:
        pairs = list_event_pairs(conn)
        kalshi = KalshiClient()
        out = []
        for p in pairs:
            pm_title = _polymarket_title(conn, p["polymarket_market_id"])
            kalshi_title = None
            try:
                m = kalshi.get_market(p["kalshi_market_ticker"])
                kalshi_title = (m.get("title") or m.get("subtitle")) if m else None
            except Exception:
                pass
            out.append(
                ComparePairItem(
                    id=p["id"],
                    label=p.get("label"),
                    polymarket_market_id=p["polymarket_market_id"],
                    polymarket_asset_id=p.get("polymarket_asset_id"),
                    kalshi_event_ticker=p["kalshi_event_ticker"],
                    kalshi_market_ticker=p["kalshi_market_ticker"],
                    polymarket_title=pm_title,
                    kalshi_title=kalshi_title,
                )
            )
        return CompareListResponse(pairs=out)
    finally:
        conn.close()


@router.get(
    "/compare/{pair_id}",
    response_model=CompareDetailResponse,
    responses={404: {"description": "Pair not found"}},
)
def events_compare_detail(pair_id: int) -> CompareDetailResponse | JSONResponse:
    """Get one event pair with full Polymarket and Kalshi metadata."""
    conn = _get_conn()
    try:
        p = get_event_pair(conn, pair_id)
        if not p:
            return JSONResponse(status_code=404, content={"detail": f"Pair {pair_id} not found", "code": "not_found"})
        pm_row = conn.execute(
            "SELECT market_id, title, category, outcomes FROM markets WHERE market_id = ?",
            [p["polymarket_market_id"]],
        ).fetchone()
        polymarket = {}
        if pm_row:
            polymarket = {"market_id": pm_row[0], "title": pm_row[1], "category": pm_row[2], "outcomes": pm_row[3]}
        kalshi_data = {}
        try:
            k = KalshiClient()
            kalshi_data = k.get_market(p["kalshi_market_ticker"])
        except Exception:
            pass
        return CompareDetailResponse(
            id=p["id"],
            label=p.get("label"),
            polymarket_market_id=p["polymarket_market_id"],
            polymarket_asset_id=p.get("polymarket_asset_id"),
            kalshi_event_ticker=p["kalshi_event_ticker"],
            kalshi_market_ticker=p["kalshi_market_ticker"],
            polymarket=polymarket,
            kalshi=kalshi_data or {},
        )
    finally:
        conn.close()
