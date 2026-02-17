"""Sim subcommand: run, report."""

import typer

app = typer.Typer(help="Simulation and strategy runs")


@app.command("run")
def run_sim(
    ctx: typer.Context,
    strategy: str = typer.Option(..., "--strategy", "-s", help="Strategy name"),
    market: str | None = typer.Option(None, "--market", "-m", help="Market ID (default: all)"),
) -> None:
    """Run a strategy in simulation (replay-driven)."""
    # Phase 4
    typer.echo("Sim run (stub)...")


@app.command("report")
def report(
    ctx: typer.Context,
    run_id: str = typer.Option(..., "--run-id", help="Simulation run ID"),
) -> None:
    """Show report for a simulation run."""
    # Phase 4
    typer.echo("Sim report (stub)...")
