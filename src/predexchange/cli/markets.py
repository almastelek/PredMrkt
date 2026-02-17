"""Markets subcommand: discover, list."""

from __future__ import annotations

import typer

from predexchange.ingestion.polymarket.gamma import fetch_markets, select_top_markets
from predexchange.storage.db import get_connection, init_schema
from predexchange.storage.markets import list_markets as storage_list_markets
from predexchange.storage.markets import set_tracked_markets, upsert_markets

app = typer.Typer(help="Market discovery and listing")


@app.command("discover")
def discover(
    ctx: typer.Context,
    limit: int = typer.Option(100, "--limit", "-n", help="Max markets to fetch"),
    update_tracked: bool = typer.Option(
        True, "--update-tracked/--no-update-tracked", help="Update tracked set from selector"
    ),
) -> None:
    """Fetch market metadata from Polymarket Gamma API and update local cache."""
    settings = ctx.obj["settings"]
    db_path = settings.db_path
    conn = get_connection(db_path)
    init_schema(conn)
    try:
        markets = fetch_markets(
            base_url=settings.gamma_api_base,
            limit=limit,
            active_only=True,
        )
        upsert_markets(conn, markets)
        if update_tracked:
            selected = select_top_markets(
                markets,
                track_count=settings.track_count,
                active_only=True,
                min_volume_24h=settings.min_volume_24h,
                min_liquidity=settings.min_liquidity,
                category_allowlist=settings.category_allowlist or None,
                category_denylist=settings.category_denylist or None,
                pinned_market_ids=settings.pinned_markets or None,
            )
            set_tracked_markets(conn, [m.market_id for m in selected], venue="polymarket")
        typer.echo(f"Discovered and cached {len(markets)} markets.")
        if update_tracked:
            typer.echo(f"Tracking {len(selected)} markets.")
    finally:
        conn.close()


@app.command("list")
def list_markets(
    ctx: typer.Context,
    tracked_only: bool = typer.Option(False, "--tracked", help="Show only tracked markets"),
) -> None:
    """List markets in local cache."""
    settings = ctx.obj["settings"]
    conn = get_connection(settings.db_path)
    init_schema(conn)
    try:
        rows = storage_list_markets(conn, tracked_only=tracked_only)
        for r in rows:
            title = (r.get("title") or "")[:60]
            typer.echo(f"  {r['market_id'][:20]}...  {r.get('volume_24h', 0):.0f}  {title}")
        typer.echo(f"Total: {len(rows)} markets")
    finally:
        conn.close()
