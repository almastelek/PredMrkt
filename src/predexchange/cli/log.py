"""Log subcommand: export, stats."""

import typer

app = typer.Typer(help="Raw event log export and statistics")


@app.command("export")
def export(
    ctx: typer.Context,
    market: str | None = typer.Option(None, "--market", "-m", help="Filter by market ID"),
    output: str = typer.Option("events.parquet", "--output", "-o", help="Output path"),
) -> None:
    """Export raw events to Parquet."""
    # Implemented in Phase 1e
    typer.echo("Export (stub)...")


@app.command("stats")
def stats(ctx: typer.Context) -> None:
    """Show event log statistics (counts, date range, by market)."""
    # Implemented in Phase 1e
    typer.echo("Log stats (stub)...")
