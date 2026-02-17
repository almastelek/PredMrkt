"""Polymarket CLOB WebSocket client - connect, subscribe, receive, reconnect."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Callable

import structlog
import websockets
from websockets.asyncio.client import ClientConnection

log = structlog.get_logger(__name__)


def _parse_message(raw: str) -> dict[str, Any] | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def run_ws_ingestion(
    ws_url: str,
    asset_ids: list[str],
    on_message: Callable[[dict[str, Any], int], None],
    *,
    reconnect_base_delay_sec: float = 1.0,
    reconnect_max_delay_sec: float = 60.0,
    reconnect_max_retries: int = 0,
    stop_event: asyncio.Event | None = None,
) -> None:
    """
    Connect to Polymarket CLOB WebSocket, subscribe to asset_ids, and call on_message for each message.
    on_message(payload_dict, ingest_ts_ms). Runs until stop_event is set or connection fails permanently.
    Reconnect with exponential backoff; resubscribe on each reconnect.
    """
    stop = stop_event or asyncio.Event()
    delay = reconnect_base_delay_sec
    retries = 0

    while not stop.is_set():
        try:
            async with websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            ) as ws:
                delay = reconnect_base_delay_sec
                retries = 0
                log.info("ws_connected", url=ws_url, asset_count=len(asset_ids))

                # Subscribe to market channel with asset IDs
                sub = {"type": "MARKET", "assets_ids": asset_ids}
                await ws.send(json.dumps(sub))
                log.info("ws_subscribed", assets=len(asset_ids))

                while not stop.is_set():
                    raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                    ingest_ts = int(time.time() * 1000)
                    msg = _parse_message(raw)
                    if msg is not None:
                        on_message(msg, ingest_ts)
        except asyncio.CancelledError:
            log.info("ws_cancelled")
            break
        except Exception as e:
            log.warning("ws_error", error=str(e), delay=delay)
            if reconnect_max_retries and retries >= reconnect_max_retries:
                log.error("ws_max_retries_reached")
                break
            retries += 1
            await asyncio.sleep(delay)
            delay = min(delay * 2, reconnect_max_delay_sec)

    log.info("ws_ingestion_stopped")


async def stream_events(
    ws_url: str,
    asset_ids: list[str],
    *,
    reconnect_base_delay_sec: float = 1.0,
    reconnect_max_delay_sec: float = 60.0,
) -> AsyncIterator[tuple[dict[str, Any], int]]:
    """
    Async generator that yields (payload_dict, ingest_ts_ms) for each WebSocket message.
    Reconnects and resubscribes on disconnect.
    """
    queue: asyncio.Queue[tuple[dict[str, Any], int] | None] = asyncio.Queue()
    sentinel = None

    def on_message(msg: dict[str, Any], ingest_ts: int) -> None:
        try:
            queue.put_nowait((msg, ingest_ts))
        except asyncio.QueueFull:
            pass

    async def run() -> None:
        await run_ws_ingestion(
            ws_url,
            asset_ids,
            on_message,
            reconnect_base_delay_sec=reconnect_base_delay_sec,
            reconnect_max_delay_sec=reconnect_max_delay_sec,
        )
        queue.put_nowait(sentinel)

    task = asyncio.create_task(run())
    try:
        while True:
            item = await queue.get()
            if item is sentinel:
                break
            yield item
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
