"""Replay subcommand: run, list."""

import typer

app = typer.Typer(help="Deterministic replay of event log")


@app.command("run")
def run_replay(
    ctx: typer.Context,
    market: str = typer.Option(..., "--market", "-m", help="Market ID"),
    start: str | None = typer.Option(None, "--start", help="Start time (ISO or ms)"),
    end: str | None = typer.Option(None, "--end", help="End time (ISO or ms)"),
    speed: str = typer.Option("1x", "--speed", help="Speed multiplier (1x, 10x, 50x)"),
) -> None:
    """Run deterministic replay for a market and time window."""
    # Phase 3a
    typer.echo("Replay run (stub)...")


@app.command("list")
def list_runs(ctx: typer.Context) -> None:
    """List replay/simulation runs."""
    # Phase 3a
    typer.echo("Replay list (stub)...")
