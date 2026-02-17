"""Markets subcommand: discover, list."""

import typer

app = typer.Typer(help="Market discovery and listing")


@app.command("discover")
def discover(
    ctx: typer.Context,
    limit: int = typer.Option(100, "--limit", "-n", help="Max markets to fetch"),
) -> None:
    """Fetch market metadata from Polymarket Gamma API and update local cache."""
    # Implemented in Phase 1c
    typer.echo("Discovering markets (stub)...")


@app.command("list")
def list_markets(
    ctx: typer.Context,
    tracked_only: bool = typer.Option(False, "--tracked", help="Show only tracked markets"),
) -> None:
    """List markets in local cache."""
    # Implemented in Phase 1c
    typer.echo("Listing markets (stub)...")
