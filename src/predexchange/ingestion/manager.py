"""Ingestion orchestrator - WebSocket + raw event persistence."""

from __future__ import annotations

import asyncio
import signal
import time
from pathlib import Path
from typing import Any

import structlog

from predexchange.ingestion.polymarket.ws import run_ws_ingestion
from predexchange.storage.db import get_connection, init_schema
from predexchange.storage.event_log import append_raw_events_batch, prepare_polymarket_rows
from predexchange.storage.markets import get_tracked_asset_ids

log = structlog.get_logger(__name__)


class IngestionManager:
    """Runs WebSocket ingestion and persists raw events to DuckDB."""

    def __init__(
        self,
        db_path: str | Path,
        ws_url: str,
        event_batch_size: int = 100,
        reconnect_base_delay_sec: float = 1.0,
        reconnect_max_delay_sec: float = 60.0,
        reconnect_max_retries: int = 0,
        orderbook_aggregator: Any = None,
    ):
        self.db_path = Path(db_path)
        self.ws_url = ws_url
        self.event_batch_size = event_batch_size
        self.reconnect_base_delay_sec = reconnect_base_delay_sec
        self.reconnect_max_delay_sec = reconnect_max_delay_sec
        self.reconnect_max_retries = reconnect_max_retries
        self.orderbook_aggregator = orderbook_aggregator
        self._conn = None
        self._batch: list[tuple[str, str, str, str, str | None, int | None, int, str]] = []
        self._msg_count = 0
        self._start_ts: float | None = None

    def _get_conn(self):
        if self._conn is None:
            self._conn = get_connection(self.db_path)
            init_schema(self._conn)
        return self._conn

    def _flush_batch(self) -> None:
        if not self._batch:
            return
        conn = self._get_conn()
        append_raw_events_batch(conn, self._batch)
        self._batch = []

    def _on_message(self, payload: dict[str, Any] | list[Any], ingest_ts: int) -> None:
        """Process one or more messages (server may send a list of events)."""
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    self._on_message_one(item, ingest_ts)
        elif isinstance(payload, dict):
            self._on_message_one(payload, ingest_ts)

    def _on_message_one(self, payload: dict[str, Any], ingest_ts: int) -> None:
        self._msg_count += 1
        if self.orderbook_aggregator is not None:
            self.orderbook_aggregator.on_message(payload, ingest_ts)
        for row in prepare_polymarket_rows(payload, ingest_ts):
            self._batch.append(row)
        if len(self._batch) >= self.event_batch_size:
            self._flush_batch()

    async def run(self, stop_event: asyncio.Event | None = None) -> None:
        """Run ingestion until stop_event is set."""
        conn = self._get_conn()
        asset_ids = get_tracked_asset_ids(conn)
        if not asset_ids:
            log.warning("no_tracked_assets", msg="Run 'predex markets discover' first to track markets.")
            return
        self._start_ts = time.time()
        stop = stop_event or asyncio.Event()
        await run_ws_ingestion(
            self.ws_url,
            asset_ids,
            self._on_message,
            reconnect_base_delay_sec=self.reconnect_base_delay_sec,
            reconnect_max_delay_sec=self.reconnect_max_delay_sec,
            reconnect_max_retries=self.reconnect_max_retries,
            stop_event=stop,
        )
        self._flush_batch()
        log.info("ingestion_stopped", total_messages=self._msg_count)

    def get_status(self) -> dict[str, Any]:
        """Return current status: msg_count, elapsed_sec, msgs_per_sec."""
        elapsed = (time.time() - self._start_ts) if self._start_ts else 0
        return {
            "msg_count": self._msg_count,
            "elapsed_sec": round(elapsed, 1),
            "msgs_per_sec": round(self._msg_count / elapsed, 2) if elapsed > 0 else 0,
        }

    def close(self) -> None:
        self._flush_batch()
        if self._conn is not None:
            self._conn.close()
            self._conn = None
