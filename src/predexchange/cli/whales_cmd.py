"""Whales subcommand: ingest large trades from Polymarket Data API."""

from __future__ import annotations

import httpx
import typer

from predexchange.config import get_settings
from predexchange.ingestion.polymarket.data_api import PolymarketDataApiClient, normalize_trade
from predexchange.storage.db import get_connection, init_schema
from predexchange.storage.whales import get_ingestion_cursor, insert_trades, upsert_ingestion_cursor

app = typer.Typer(help="Whale/insider data ingestion and wallet tools")
MAX_DATA_API_OFFSET = 3000


@app.command("ingest")
def ingest(
    min_cash: float | None = typer.Option(
        None, "--min-cash", help="Minimum trade cash notional filter for Data API /trades"
    ),
    page_limit: int | None = typer.Option(None, "--page-limit", help="Page size for /trades (max 10000)"),
    max_pages: int | None = typer.Option(None, "--max-pages", help="Max pages to fetch this run"),
    from_offset: int | None = typer.Option(
        None,
        "--from-offset",
        help="Start offset override (clamped to Data API max offset 3000)",
    ),
    reset_offset: bool = typer.Option(
        False,
        "--reset-offset",
        help="Ignore saved cursors and start from newest pages",
    ),
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
        saved_offset = 0
        if not reset_offset:
            raw = get_ingestion_cursor(conn, "whales_offset")
            if raw:
                try:
                    saved_offset = max(0, int(raw))
                except ValueError:
                    saved_offset = 0
        start_offset = max(0, from_offset) if from_offset is not None else saved_offset
        if start_offset > MAX_DATA_API_OFFSET:
            typer.echo(
                f"Saved/start offset {start_offset} exceeds Data API max ({MAX_DATA_API_OFFSET}); "
                "switching to rolling mode from offset=0."
            )
            start_offset = 0
        raw_ts = None if reset_offset else get_ingestion_cursor(conn, "whales_last_ts_ms")
        last_seen_ts_ms = 0
        if raw_ts:
            try:
                last_seen_ts_ms = max(0, int(raw_ts))
            except ValueError:
                last_seen_ts_ms = 0
        typer.echo(
            f"Starting ingest from offset={start_offset} (max allowed {MAX_DATA_API_OFFSET}), "
            f"last_seen_ts_ms={last_seen_ts_ms}"
        )
        total_fetched = 0
        total_inserted = 0
        current_offset = start_offset
        max_seen_ts_ms = last_seen_ts_ms
        stale_pages = 0
        for i in range(max(1, pages_value)):
            offset = current_offset
            if offset > MAX_DATA_API_OFFSET:
                typer.echo(f"Reached Data API max offset ({MAX_DATA_API_OFFSET}); stopping this run.")
                break
            try:
                rows = client.get_trades(
                    limit=limit_value,
                    offset=offset,
                    taker_only=taker_only,
                    filter_type="CASH",
                    filter_amount=min_cash_value,
                )
            except httpx.HTTPStatusError as e:
                body = ""
                try:
                    body = e.response.text or ""
                except Exception:
                    body = ""
                body_snippet = body[:500].replace("\n", " ").strip()
                typer.echo(
                    f"page={i+1} offset={offset} failed with HTTP {e.response.status_code}; "
                    f"saved progress at offset={current_offset}. Re-run to continue or use --from-offset."
                )
                if body_snippet:
                    typer.echo(f"response: {body_snippet}")
                break
            except httpx.HTTPError as e:
                typer.echo(
                    f"page={i+1} offset={offset} failed ({e}); "
                    f"saved progress at offset={current_offset}. Re-run to continue or use --from-offset."
                )
                break
            if not rows:
                typer.echo(f"No rows at offset={offset}; stopping.")
                break
            normalized = [normalize_trade(r) for r in rows]
            page_max_ts = max((int(r.get("timestamp_ms") or 0) for r in normalized), default=0)
            page_new = [r for r in normalized if int(r.get("timestamp_ms") or 0) > last_seen_ts_ms]
            if page_max_ts <= last_seen_ts_ms:
                stale_pages += 1
            else:
                stale_pages = 0
            if page_max_ts > max_seen_ts_ms:
                max_seen_ts_ms = page_max_ts
            inserted = insert_trades(conn, page_new)
            total_fetched += len(rows)
            total_inserted += inserted
            typer.echo(
                f"page={i+1} fetched={len(rows)} new_rows={len(page_new)} inserted={inserted} "
                f"page_max_ts={page_max_ts}"
            )
            current_offset += len(rows)
            effective_offset = min(current_offset, MAX_DATA_API_OFFSET)
            upsert_ingestion_cursor(conn, "whales_offset", str(effective_offset))
            upsert_ingestion_cursor(conn, "whales_last_ts_ms", str(max_seen_ts_ms))
            if len(rows) < limit_value:
                break
            if stale_pages >= 2:
                typer.echo("Encountered only stale pages (older than last seen timestamp); stopping early.")
                break
        effective_offset = min(current_offset, MAX_DATA_API_OFFSET)
        upsert_ingestion_cursor(conn, "whales_offset", str(effective_offset))
        upsert_ingestion_cursor(conn, "whales_last_ts_ms", str(max_seen_ts_ms))
        conn.commit()
        typer.echo(
            f"Done. fetched={total_fetched} inserted={total_inserted} "
            f"next_offset={effective_offset} last_ts_ms={max_seen_ts_ms}"
        )
    finally:
        conn.close()

