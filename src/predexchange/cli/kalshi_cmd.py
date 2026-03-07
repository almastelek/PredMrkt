"""Kalshi subcommand: verify client and list events/markets."""

from __future__ import annotations

import json
import typer

from predexchange.ingestion.kalshi.client import KalshiClient

app = typer.Typer(help="Kalshi API: list events and markets (verify client)")


@app.command("events")
def events(
    limit: int = typer.Option(5, "--limit", "-n", help="Max events to fetch"),
    status: str = typer.Option("open", "--status", "-s", help="Filter: open, closed, settled"),
    nested: bool = typer.Option(False, "--markets/--no-markets", help="Include nested markets in each event"),
) -> None:
    """Fetch events from Kalshi API. Use to verify the client works."""
    client = KalshiClient()
    try:
        data = client.get_events(limit=limit, status=status or None, with_nested_markets=nested)
        events_list = data.get("events") or []
        typer.echo(f"Got {len(events_list)} events (cursor: {data.get('cursor', '') or '(end)'})")
        for i, ev in enumerate(events_list):
            title = (ev.get("title") or "")[:60]
            ticker = ev.get("event_ticker", "")
            series = ev.get("series_ticker", "")
            markets_count = len(ev.get("markets") or []) if nested else "?"
            typer.echo(f"  {i+1}. [{ticker}] {title}... (series={series}, markets={markets_count})")
    except Exception as e:
        typer.echo(typer.style(f"Error: {e}", fg="red"), err=True)
        raise typer.Exit(1)


@app.command("market")
def market(
    ticker: str = typer.Argument(..., help="Market ticker (e.g. from an event)"),
    orderbook: bool = typer.Option(False, "--orderbook", "-o", help="Fetch orderbook too"),
) -> None:
    """Fetch a single market by ticker. Use to verify the client works."""
    client = KalshiClient()
    try:
        m = client.get_market(ticker)
        typer.echo(f"Market: {m.get('ticker')}")
        typer.echo(f"  Event: {m.get('event_ticker')}")
        typer.echo(f"  Title: {m.get('title') or m.get('subtitle')}")
        typer.echo(f"  Status: {m.get('status')}")
        typer.echo(f"  Yes bid/ask: {m.get('yes_bid')} / {m.get('yes_ask')} (cents)")
        typer.echo(f"  Last price: {m.get('last_price')} (cents)")
        if orderbook:
            ob = client.get_orderbook(ticker)
            typer.echo("  Orderbook:")
            book = ob.get("orderbook", {})
            for side in ("yes", "no"):
                levels = book.get(side, [])[:5]
                typer.echo(f"    {side}: {levels}")
    except Exception as e:
        typer.echo(typer.style(f"Error: {e}", fg="red"), err=True)
        raise typer.Exit(1)


@app.command("orderbook")
def orderbook(ticker: str = typer.Argument(..., help="Market ticker")) -> None:
    """Fetch orderbook for a market."""
    client = KalshiClient()
    try:
        ob = client.get_orderbook(ticker)
        typer.echo(json.dumps(ob, indent=2))
    except Exception as e:
        typer.echo(typer.style(f"Error: {e}", fg="red"), err=True)
        raise typer.Exit(1)
