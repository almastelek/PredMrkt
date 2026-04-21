"""Whales subcommand: ingest large trades from Polymarket Data API."""

from __future__ import annotations

import typer

from predexchange.config import get_settings
from predexchange.ingestion.polymarket.data_api import PolymarketDataApiClient
from predexchange.signals.build import run_signals_pipeline
from predexchange.storage.db import get_connection, init_schema
from predexchange.whales.ingest import run_whales_ingest_once

app = typer.Typer(help="Whale/insider data ingestion and wallet tools")


@app.command("ingest")
def ingest(
    min_cash: float | None = typer.Option(
        None, "--min-cash", help="Minimum trade cash notional filter for Data API /trades"
    ),
    page_limit: int | None = typer.Option(None, "--page-limit", help="Page size for /trades (max 10000)"),
    max_pages: int | None = typer.Option(None, "--max-pages", help="Max pages to fetch this run"),
    from_offset: int | None = typer.Option(
        None,
        "--from-offset",
        help="Start offset override (clamped to Data API max offset 3000)",
    ),
    reset_offset: bool = typer.Option(
        False,
        "--reset-offset",
        help="Ignore saved cursors and start from newest pages",
    ),
    taker_only: bool = typer.Option(True, "--taker-only/--all-fills", help="Only taker fills (default true)"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Config profile"),
) -> None:
    """Ingest large trades globally from Polymarket Data API into DuckDB."""
    settings = get_settings(profile)
    min_cash_value = float(min_cash if min_cash is not None else settings.whale_min_cash_filter)
    limit_value = int(page_limit if page_limit is not None else settings.whale_ingest_page_limit)
    pages_value = int(max_pages if max_pages is not None else settings.whale_ingest_max_pages)

    client = PolymarketDataApiClient(base_url=settings.data_api_base)
    conn = get_connection(settings.db_path, read_only=False)
    try:
        init_schema(conn)
        typer.echo("Starting whales ingest...")
        stats = run_whales_ingest_once(
            conn=conn,
            client=client,
            min_cash=min_cash_value,
            page_limit=limit_value,
            max_pages=pages_value,
            taker_only=taker_only,
            from_offset=from_offset,
            reset_offset=reset_offset,
        )
        conn.commit()
        typer.echo(
            f"Done. fetched={stats['fetched']} inserted={stats['inserted']} "
            f"next_offset={stats['next_offset']} last_ts_ms={stats['last_ts_ms']}"
        )
        if stats.get("last_error"):
            typer.echo(f"last_error: {stats['last_error']}")
    finally:
        conn.close()


@app.command("signals")
def signals(
    lookback_days: int = typer.Option(60, "--lookback-days", help="Days of trades to consider"),
    gap_minutes: int = typer.Option(30, "--gap-minutes", help="Gap that closes an episode"),
    score_since_hours: int = typer.Option(168, "--score-since-hours", help="Score episodes from the last N hours"),
    max_alerts: int = typer.Option(1000, "--max-alerts", help="Max alerts scored per run"),
    forward_returns_limit: int = typer.Option(500, "--forward-returns-limit", help="Max episodes to attempt fwd-return fill"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Config profile"),
) -> None:
    """Build episodes + wallet stats + alert scores from existing data_api_trades."""
    settings = get_settings(profile)
    conn = get_connection(settings.db_path, read_only=False)
    try:
        init_schema(conn)
        typer.echo("Building wallet signals...")
        stats = run_signals_pipeline(
            conn,
            lookback_days=lookback_days,
            gap_ms=int(gap_minutes) * 60 * 1000,
            score_since_hours=score_since_hours,
            max_alerts=max_alerts,
            forward_returns_limit=forward_returns_limit,
        )
        conn.commit()
        typer.echo(
            "Done. "
            f"episodes={stats['episodes_upserted']} "
            f"categories={stats['market_meta_updated']} "
            f"fwd_returns={stats['forward_returns_filled']} "
            f"wallet_stats={stats['wallet_stats_upserted']} "
            f"alerts={stats['alerts_scored']}"
        )
    finally:
        conn.close()

