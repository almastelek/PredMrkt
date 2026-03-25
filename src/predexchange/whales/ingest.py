"""Shared whales ingest routine (used by CLI and API background task)."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from predexchange.ingestion.polymarket.data_api import PolymarketDataApiClient, normalize_trade
from predexchange.storage.whales import get_ingestion_cursor, insert_trades, upsert_ingestion_cursor

log = structlog.get_logger(__name__)

MAX_DATA_API_OFFSET = 3000


def run_whales_ingest_once(
    *,
    conn: Any,
    client: PolymarketDataApiClient,
    min_cash: float,
    page_limit: int,
    max_pages: int,
    taker_only: bool = True,
    from_offset: int | None = None,
    reset_offset: bool = False,
) -> dict[str, Any]:
    """
    Run one ingest cycle and return stats.

    Uses a rolling window approach compatible with Data API offset cap.
    Persists cursors:
      - whales_offset (clamped to <= 3000)
      - whales_last_ts_ms
    """
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
        start_offset = 0

    raw_ts = None if reset_offset else get_ingestion_cursor(conn, "whales_last_ts_ms")
    last_seen_ts_ms = 0
    if raw_ts:
        try:
            last_seen_ts_ms = max(0, int(raw_ts))
        except ValueError:
            last_seen_ts_ms = 0

    total_fetched = 0
    total_inserted = 0
    current_offset = start_offset
    max_seen_ts_ms = last_seen_ts_ms
    stale_pages = 0
    last_error: str | None = None

    for _i in range(max(1, max_pages)):
        offset = current_offset
        if offset > MAX_DATA_API_OFFSET:
            break
        try:
            rows = client.get_trades(
                limit=page_limit,
                offset=offset,
                taker_only=taker_only,
                filter_type="CASH",
                filter_amount=min_cash,
            )
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}"
            try:
                txt = (e.response.text or "").strip()
                if txt:
                    last_error += f": {txt[:200]}"
            except Exception:
                pass
            break
        except httpx.HTTPError as e:
            last_error = str(e)
            break

        if not rows:
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

        current_offset += len(rows)
        effective_offset = min(current_offset, MAX_DATA_API_OFFSET)
        upsert_ingestion_cursor(conn, "whales_offset", str(effective_offset))
        upsert_ingestion_cursor(conn, "whales_last_ts_ms", str(max_seen_ts_ms))

        if len(rows) < page_limit:
            break
        if stale_pages >= 2:
            break

    effective_offset = min(current_offset, MAX_DATA_API_OFFSET)
    upsert_ingestion_cursor(conn, "whales_offset", str(effective_offset))
    upsert_ingestion_cursor(conn, "whales_last_ts_ms", str(max_seen_ts_ms))

    stats = {
        "fetched": total_fetched,
        "inserted": total_inserted,
        "next_offset": effective_offset,
        "last_ts_ms": max_seen_ts_ms,
        "last_error": last_error,
    }
    log.info("whales_ingest_once", **stats)
    return stats

