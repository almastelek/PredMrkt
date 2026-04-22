"""Wallet signals API: episodes, wallet stats, alerts, and pipeline runner."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from predexchange.api import runtime
from predexchange.api.db import get_api_connection
from predexchange.api.schemas import (
    SignalAlert,
    SignalAlertsResponse,
    SignalsRunResponse,
    WalletEpisode,
    WalletEpisodesResponse,
    WalletSignalStats,
    WalletSignalStatsResponse,
)
from predexchange.config import get_settings
from predexchange.signals.build import config_from_settings, run_signals_pipeline
from predexchange.storage.db import init_schema
from predexchange.storage.signals import get_wallet_stats, list_alerts, list_episodes

router = APIRouter()


def _conn():
    return get_api_connection()


@router.get("/whales/episodes", response_model=WalletEpisodesResponse)
def whales_episodes(
    wallet: str | None = Query(None),
    condition_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> WalletEpisodesResponse:
    conn = _conn()
    try:
        init_schema(conn)
        episodes = list_episodes(
            conn, wallet=wallet, condition_id=condition_id, limit=limit
        )
    finally:
        conn.close()
    return WalletEpisodesResponse(episodes=[WalletEpisode(**e) for e in episodes])


@router.get("/whales/wallets/{address}/stats", response_model=WalletSignalStatsResponse)
def whales_wallet_stats(address: str) -> WalletSignalStatsResponse:
    conn = _conn()
    try:
        init_schema(conn)
        s = get_wallet_stats(conn, address)
    finally:
        conn.close()
    return WalletSignalStatsResponse(stats=WalletSignalStats(**s) if s else None)


@router.get("/whales/signals", response_model=SignalAlertsResponse)
def whales_signals(
    limit: int = Query(50, ge=1, le=500),
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    market_category: str | None = Query(None),
    include_sports: bool = Query(True),
) -> SignalAlertsResponse:
    conn = _conn()
    try:
        init_schema(conn)
        alerts = list_alerts(
            conn,
            min_score=min_score,
            market_category=market_category,
            include_sports=include_sports,
            limit=limit,
        )
    finally:
        conn.close()
    return SignalAlertsResponse(alerts=[SignalAlert(**a) for a in alerts])


@router.post("/whales/signals/run", response_model=SignalsRunResponse)
def whales_signals_run(
    lookback_days: int | None = Query(None, ge=1, le=365),
    gap_minutes: int | None = Query(None, ge=1, le=720),
    score_since_hours: int | None = Query(None, ge=1, le=24 * 30),
    max_alerts: int | None = Query(None, ge=1, le=10000),
    forward_returns_limit: int | None = Query(None, ge=0, le=10000),
) -> SignalsRunResponse:
    settings = get_settings(runtime.config_profile)
    cfg = config_from_settings(settings)
    conn = _conn()
    try:
        init_schema(conn)
        try:
            stats = run_signals_pipeline(
                conn,
                config=cfg,
                lookback_days=lookback_days,
                gap_ms=int(gap_minutes) * 60 * 1000 if gap_minutes is not None else None,
                score_since_hours=score_since_hours,
                max_alerts=max_alerts,
                forward_returns_limit=forward_returns_limit,
            )
            conn.commit()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
    return SignalsRunResponse(**stats)
