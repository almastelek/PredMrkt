"""Whales subcommand: ingest large trades from Polymarket Data API."""

from __future__ import annotations

import typer

from predexchange.config import get_settings
from predexchange.ingestion.polymarket.data_api import PolymarketDataApiClient, normalize_trade
from predexchange.storage.db import get_connection, init_schema
from predexchange.storage.whales import insert_trades, upsert_ingestion_cursor

app = typer.Typer(help="Whale/insider data ingestion and wallet tools")


@app.command("ingest")
def ingest(
    min_cash: float | None = typer.Option(
        None, "--min-cash", help="Minimum trade cash notional filter for Data API /trades"
    ),
    page_limit: int | None = typer.Option(None, "--page-limit", help="Page size for /trades (max 10000)"),
    max_pages: int | None = typer.Option(None, "--max-pages", help="Max pages to fetch this run"),
    taker_only: bool = typer.Option(True, "--taker-only/--all-fills", help="Only taker fills (default true)"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Config profile"),
) -> None:
    """Ingest large trades globally from Polymarket Data API into DuckDB."""
    settings = get_settings(profile)
    min_cash_value = float(min_cash if min_cash is not None else settings.whale_min_cash_filter)
    limit_value = int(page_limit if page_limit is not None else settings.whale_ingest_page_limit)
    pages_value = int(max_pages if max_pages is not None else settings.whale_ingest_max_pages)

    client = PolymarketDataApiClient(base_url=settings.data_api_base)
    conn = get_connection(settings.db_path, read_only=False)
    try:
        init_schema(conn)
        total_fetched = 0
        total_inserted = 0
        for i in range(max(1, pages_value)):
            offset = i * limit_value
            rows = client.get_trades(
                limit=limit_value,
                offset=offset,
                taker_only=taker_only,
                filter_type="CASH",
                filter_amount=min_cash_value,
            )
            if not rows:
                break
            normalized = [normalize_trade(r) for r in rows]
            inserted = insert_trades(conn, normalized)
            total_fetched += len(rows)
            total_inserted += inserted
            typer.echo(f"page={i+1} fetched={len(rows)} inserted={inserted}")
            if len(rows) < limit_value:
                break
        upsert_ingestion_cursor(conn, "whales_offset", str(total_fetched))
        conn.commit()
        typer.echo(f"Done. fetched={total_fetched} inserted={total_inserted}")
    finally:
        conn.close()

