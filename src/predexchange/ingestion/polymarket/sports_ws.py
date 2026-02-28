"""Polymarket Sports WebSocket - live scores and game state. No subscription required."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable

import structlog
import websockets

log = structlog.get_logger(__name__)

SPORTS_WS_URL = "wss://sports-api.polymarket.com/ws"


def _parse_message(raw: str) -> dict[str, Any] | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def run_sports_ws(
    on_message: Callable[[dict[str, Any], int], None],
    *,
    reconnect_base_delay_sec: float = 1.0,
    reconnect_max_delay_sec: float = 60.0,
    stop_event: asyncio.Event | None = None,
) -> None:
    """
    Connect to Polymarket Sports WS, respond to ping with pong, and call on_message for each sport_result.
    on_message(payload_dict, ingest_ts_ms). No subscription required.
    """
    stop = stop_event or asyncio.Event()
    delay = reconnect_base_delay_sec

    while not stop.is_set():
        try:
            async with websockets.connect(
                SPORTS_WS_URL,
                ping_interval=None,
                ping_timeout=None,
                close_timeout=5,
            ) as ws:
                delay = reconnect_base_delay_sec
                log.info("sports_ws_connected", url=SPORTS_WS_URL)

                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=12.0)
                    except asyncio.TimeoutError:
                        continue
                    if raw == "ping":
                        await ws.send("pong")
                        continue
                    ingest_ts = int(time.time() * 1000)
                    msg = _parse_message(raw)
                    if msg is not None and isinstance(msg, dict) and "gameId" in msg:
                        on_message(msg, ingest_ts)
        except asyncio.CancelledError:
            log.info("sports_ws_cancelled")
            break
        except Exception as e:
            log.warning("sports_ws_error", error=str(e), delay=delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, reconnect_max_delay_sec)

    log.info("sports_ws_stopped")
