"""Track subcommand: start, status, stop."""

import typer

app = typer.Typer(help="Start/stop tracking and show status")


@app.command("start")
def start(
    ctx: typer.Context,
    n: int = typer.Option(None, "--n", "-n", help="Number of markets to track (overrides config)"),
) -> None:
    """Start ingestion: discover markets, connect WebSocket, persist events."""
    # Implemented in Phase 1e
    typer.echo("Starting track (stub)...")


@app.command("status")
def status(ctx: typer.Context) -> None:
    """Show connection health, msg/sec, active markets."""
    # Implemented in Phase 1e
    typer.echo("Track status (stub)...")


@app.command("stop")
def stop(ctx: typer.Context) -> None:
    """Stop ingestion gracefully."""
    # Implemented in Phase 1e
    typer.echo("Stopping track (stub)...")
