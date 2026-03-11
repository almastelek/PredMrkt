"""CLI for event pairs (Polymarket <-> Kalshi): list and add."""

from __future__ import annotations

import typer

from predexchange.config import get_settings
from predexchange.storage.db import get_connection, init_schema
from predexchange.storage.event_pairs import add_pair, list_pairs

app = typer.Typer(help="Event pairs: list and add Polymarket <-> Kalshi links")


@app.command("list")
def pairs_list(profile: str | None = typer.Option(None, "--profile", "-p", help="Config profile")) -> None:
    """List all event pairs."""
    settings = get_settings(profile)
    conn = get_connection(settings.db_path, read_only=True)
    try:
        pairs = list_pairs(conn)
        if not pairs:
            typer.echo("No pairs yet. Add one with: predex pairs add --polymarket-market-id <id> --kalshi-event-ticker <ticker> --kalshi-market-ticker <ticker>")
            return
        for p in pairs:
            label = p.get("label") or "(no label)"
            typer.echo(f"  {p['id']}. {label}")
            typer.echo(f"      Polymarket: {p['polymarket_market_id']}" + (f" (asset: {p['polymarket_asset_id']})" if p.get("polymarket_asset_id") else ""))
            typer.echo(f"      Kalshi: {p['kalshi_event_ticker']} / {p['kalshi_market_ticker']}")
    finally:
        conn.close()


@app.command("add")
def pairs_add(
    polymarket_market_id: str = typer.Option(..., "--polymarket-market-id", "-pm", help="Polymarket market_id (condition_id)"),
    kalshi_event_ticker: str = typer.Option(..., "--kalshi-event-ticker", "-ke", help="Kalshi event_ticker"),
    kalshi_market_ticker: str = typer.Option(..., "--kalshi-market-ticker", "-km", help="Kalshi market ticker"),
    polymarket_asset_id: str | None = typer.Option(None, "--polymarket-asset-id", "-pa", help="Polymarket asset/token id (optional)"),
    label: str | None = typer.Option(None, "--label", "-l", help="Short label for the pair"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Config profile"),
) -> None:
    """Add a new event pair."""
    settings = get_settings(profile)
    conn = get_connection(settings.db_path, read_only=False)
    try:
        init_schema(conn)
        pair_id = add_pair(
            conn,
            polymarket_market_id=polymarket_market_id,
            kalshi_event_ticker=kalshi_event_ticker,
            kalshi_market_ticker=kalshi_market_ticker,
            polymarket_asset_id=polymarket_asset_id,
            label=label,
        )
        conn.commit()
        typer.echo(f"Added pair id={pair_id}")
    finally:
        conn.close()
