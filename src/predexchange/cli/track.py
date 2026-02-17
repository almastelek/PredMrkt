"""Track subcommand: start, status, stop."""

from __future__ import annotations

import asyncio
import signal
import sys

import typer

from predexchange.ingestion.manager import IngestionManager
from predexchange.storage.db import get_connection, init_schema
from predexchange.storage.event_log import log_stats
from predexchange.storage.markets import get_tracked_asset_ids, get_tracked_market_ids

app = typer.Typer(help="Start/stop tracking and show status")


@app.command("start")
def start(
    ctx: typer.Context,
    n: int = typer.Option(None, "--n", "-n", help="Number of markets to track (overrides config)"),
) -> None:
    """Start ingestion: connect WebSocket, persist events. Run 'predex markets discover' first."""
    settings = ctx.obj["settings"]
    db_path = settings.db_path
    conn = get_connection(db_path)
    init_schema(conn)
    asset_ids = get_tracked_asset_ids(conn)
    conn.close()
    if not asset_ids:
        typer.echo("No tracked markets. Run: predex markets discover")
        raise typer.Exit(1)
    manager = IngestionManager(
        db_path=db_path,
        ws_url=settings.clob_ws_url,
        event_batch_size=settings.event_batch_size,
        reconnect_base_delay_sec=settings.reconnect_base_delay_sec,
        reconnect_max_delay_sec=settings.reconnect_max_delay_sec,
        reconnect_max_retries=settings.reconnect_max_retries,
    )
    stop_event = asyncio.Event()

    def shutdown() -> None:
        stop_event.set()

    loop = asyncio.new_event_loop()
    if sys.platform != "win32":
        loop.add_signal_handler(
            signal.SIGINT,
            shutdown,
        )
        loop.add_signal_handler(
            signal.SIGTERM,
            shutdown,
        )
    try:
        typer.echo("Starting ingestion (Ctrl+C to stop)...")
        loop.run_until_complete(manager.run(stop_event=stop_event))
    except KeyboardInterrupt:
        pass
    finally:
        manager.close()
        loop.close()
    typer.echo("Stopped.")


@app.command("status")
def status(ctx: typer.Context) -> None:
    """Show event log statistics and tracked market count."""
    settings = ctx.obj["settings"]
    conn = get_connection(settings.db_path)
    init_schema(conn)
    try:
        tracked = get_tracked_market_ids(conn)
        asset_count = len(get_tracked_asset_ids(conn))
        stats = log_stats(conn)
        typer.echo(f"Tracked markets: {len(tracked)}")
        typer.echo(f"Tracked asset IDs (subscriptions): {asset_count}")
        typer.echo(f"Total events in log: {stats['total_events']}")
        if stats.get("min_ingest_ts") and stats.get("max_ingest_ts"):
            typer.echo(f"Time range: {stats['min_ingest_ts']} - {stats['max_ingest_ts']} (ms)")
        if stats.get("by_market"):
            typer.echo("Top markets by event count:")
            for row in stats["by_market"][:10]:
                typer.echo(f"  {row['market_id'][:24]}...  {row['count']}")
    finally:
        conn.close()


@app.command("stop")
def stop(ctx: typer.Context) -> None:
    """Stop ingestion (when running in foreground, use Ctrl+C). This command is a no-op when not running."""
    typer.echo("Ingestion runs in foreground. Use Ctrl+C in the terminal where 'track start' is running to stop.")
