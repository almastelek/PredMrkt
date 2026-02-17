"""Sim subcommand: run, report."""

from __future__ import annotations

import typer

from predexchange.simulation.runner import get_run_result, run_simulation, save_run_result
from predexchange.simulation.strategies.mm_basic import MMInventoryStrategy
from predexchange.storage.db import get_connection, init_schema

app = typer.Typer(help="Simulation and strategy runs")

STRATEGIES = {"mm_basic": MMInventoryStrategy}


@app.command("run")
def run_sim(
    ctx: typer.Context,
    strategy: str = typer.Option(..., "--strategy", "-s", help="Strategy name (e.g. mm_basic)"),
    market: str | None = typer.Option(None, "--market", "-m", help="Market ID (required for now)"),
) -> None:
    """Run a strategy in simulation (replay-driven)."""
    if strategy not in STRATEGIES:
        typer.echo(f"Unknown strategy: {strategy}. Choose from: {list(STRATEGIES)}")
        raise typer.Exit(1)
    if not market:
        typer.echo("--market is required")
        raise typer.Exit(1)
    settings = ctx.obj["settings"]
    conn = get_connection(settings.db_path)
    init_schema(conn)
    try:
        strat_class = STRATEGIES[strategy]
        strat = strat_class()
        # Use first asset for the market (from markets table or from raw_events)
        rows = conn.execute(
            "SELECT DISTINCT asset_id FROM raw_events WHERE market_id = ? LIMIT 1",
            [market],
        ).fetchall()
        asset_id = rows[0][0] if rows else ""
        if not asset_id:
            typer.echo("No events found for that market. Run ingestion first.")
            raise typer.Exit(1)
        result = run_simulation(conn, strat, market, asset_id)
        save_run_result(conn, result)
        typer.echo(f"Run id: {result.run_id}")
        typer.echo(f"Strategy: {result.strategy_name}  Market: {result.market_id}")
        typer.echo(f"Events: {result.events_processed}  Fills: {result.fill_count}")
        typer.echo(f"Realized PnL: {result.realized_pnl:.2f}  Final inventory: {result.final_inventory:.2f}")
    finally:
        conn.close()


@app.command("report")
def report(
    ctx: typer.Context,
    run_id: str = typer.Option(..., "--run-id", help="Simulation run ID"),
) -> None:
    """Show report for a simulation run."""
    settings = ctx.obj["settings"]
    conn = get_connection(settings.db_path)
    init_schema(conn)
    try:
        result = get_run_result(conn, run_id)
        if not result:
            typer.echo(f"Run not found: {run_id}")
            raise typer.Exit(1)
        typer.echo(f"Run: {result.run_id}")
        typer.echo(f"Strategy: {result.strategy_name}  Market: {result.market_id}")
        typer.echo(f"Events processed: {result.events_processed}  Fills: {result.fill_count}")
        typer.echo(f"Realized PnL: {result.realized_pnl:.2f}")
        typer.echo(f"Final inventory: {result.final_inventory:.2f}")
    finally:
        conn.close()
