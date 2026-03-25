"""Whale/insider API routes backed by Data API ingest + DuckDB analytics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from predexchange.api import runtime
from predexchange.api.db import get_api_connection
from predexchange.api.schemas import (
    TrackWalletRequest,
    TrackedWalletsResponse,
    WalletDetailResponse,
    WalletLiveResponse,
    WhaleTradesResponse,
    WhaleWalletAgg,
    WhaleWalletsResponse,
)
from predexchange.config import get_settings
from predexchange.ingestion.polymarket.data_api import PolymarketDataApiClient
from predexchange.storage.db import init_schema
from predexchange.storage.whales import (
    list_large_trades,
    list_tracked_wallets,
    track_wallet,
    untrack_wallet,
    wallet_aggregates,
)

router = APIRouter()


def _get_conn():
    return get_api_connection()


@router.get("/whales/trades", response_model=WhaleTradesResponse)
def whales_trades(
    limit: int = Query(100, ge=1, le=500),
    min_notional: float | None = Query(None, ge=0),
) -> WhaleTradesResponse:
    settings = get_settings(runtime.config_profile)
    threshold = float(min_notional if min_notional is not None else settings.whale_min_cash_filter)
    conn = _get_conn()
    try:
        init_schema(conn)
        return WhaleTradesResponse(trades=list_large_trades(conn, min_notional=threshold, limit=limit))
    finally:
        conn.close()


@router.get("/whales/wallets", response_model=WhaleWalletsResponse)
def whales_wallets(
    limit: int = Query(100, ge=1, le=500),
    min_notional: float | None = Query(None, ge=0),
) -> WhaleWalletsResponse:
    settings = get_settings(runtime.config_profile)
    threshold = float(min_notional if min_notional is not None else settings.whale_min_cash_filter)
    conn = _get_conn()
    try:
        init_schema(conn)
        wallets = wallet_aggregates(conn, min_notional=threshold, limit=limit)
        tracked = {w["address"] for w in list_tracked_wallets(conn)}
        for w in wallets:
            w["is_tracked"] = w["wallet"] in tracked
        return WhaleWalletsResponse(wallets=[WhaleWalletAgg(**w) for w in wallets])
    finally:
        conn.close()


@router.get("/whales/tracked", response_model=TrackedWalletsResponse)
def whales_tracked() -> TrackedWalletsResponse:
    conn = _get_conn()
    try:
        init_schema(conn)
        return TrackedWalletsResponse(wallets=list_tracked_wallets(conn))
    finally:
        conn.close()


@router.post("/whales/track")
def whales_track(body: TrackWalletRequest) -> dict[str, Any]:
    conn = _get_conn()
    try:
        init_schema(conn)
        track_wallet(conn, body.address, label=body.label, notes=body.notes)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/whales/track/{address}")
def whales_untrack(address: str) -> dict[str, Any]:
    conn = _get_conn()
    try:
        init_schema(conn)
        untrack_wallet(conn, address)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.get("/whales/wallets/{address}")
def whales_wallet_detail(address: str) -> WalletDetailResponse:
    conn = _get_conn()
    try:
        init_schema(conn)
        items = wallet_aggregates(conn, min_notional=0, limit=100000)
        summary = next((w for w in items if w["wallet"] == address.lower()), None)
        tracked = next((w for w in list_tracked_wallets(conn) if w["address"] == address.lower()), None)
    finally:
        conn.close()

    summary_model = WhaleWalletAgg(**summary) if summary else None
    return WalletDetailResponse(wallet=address.lower(), summary=summary_model, tracked=tracked)


@router.get("/whales/wallets/{address}/live", response_model=WalletLiveResponse)
def whales_wallet_live(address: str) -> WalletLiveResponse:
    settings = get_settings(runtime.config_profile)
    client = PolymarketDataApiClient(base_url=settings.data_api_base)
    out: dict[str, Any] = {"wallet": address.lower()}
    try:
        out["value"] = client.get_value(address)
    except Exception:
        out["value"] = None
    try:
        out["positions"] = client.get_positions(address)
    except Exception:
        out["positions"] = None
    try:
        out["closed_positions"] = client.get_closed_positions(address)
    except Exception:
        out["closed_positions"] = None
    try:
        out["activity"] = client.get_activity(address)
    except Exception:
        out["activity"] = None
    return WalletLiveResponse(**out)

