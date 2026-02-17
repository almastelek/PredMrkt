"""Log subcommand: export, stats."""

from __future__ import annotations

import typer

from predexchange.storage.db import get_connection, init_schema
from predexchange.storage.event_log import log_stats
from predexchange.storage.export import export_events_to_parquet

app = typer.Typer(help="Raw event log export and statistics")


@app.command("export")
def export(
    ctx: typer.Context,
    market: str | None = typer.Option(None, "--market", "-m", help="Filter by market ID"),
    output: str = typer.Option("events.parquet", "--output", "-o", help="Output path"),
) -> None:
    """Export raw events to Parquet."""
    settings = ctx.obj["settings"]
    conn = get_connection(settings.db_path)
    init_schema(conn)
    try:
        count = export_events_to_parquet(conn, output, market_id=market)
        typer.echo(f"Exported {count} events to {output}")
    finally:
        conn.close()


@app.command("stats")
def stats(ctx: typer.Context) -> None:
    """Show event log statistics (counts, time range, by market)."""
    settings = ctx.obj["settings"]
    conn = get_connection(settings.db_path)
    init_schema(conn)
    try:
        s = log_stats(conn)
        typer.echo(f"Total events: {s['total_events']}")
        typer.echo(f"Min ingest_ts: {s.get('min_ingest_ts')}")
        typer.echo(f"Max ingest_ts: {s.get('max_ingest_ts')}")
        if s.get("by_market"):
            typer.echo("By market (top 20):")
            for row in s["by_market"]:
                typer.echo(f"  {row['market_id']}  {row['count']}")
    finally:
        conn.close()
