"""Textual TUI dashboard - health, market table, drill-down."""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, Static

from predexchange.ingestion.manager import IngestionManager
from predexchange.orderbook.aggregator import OrderBookAggregator


class HealthPanel(Static):
    """WS connection health and msg rate."""

    status = reactive("Starting...")
    msg_count = reactive(0)
    msgs_per_sec = reactive(0.0)

    def render(self) -> str:
        return (
            f"[bold]Status[/] {self.status}  |  "
            f"Messages: {self.msg_count}  |  "
            f"Rate: {self.msgs_per_sec:.1f}/s"
        )


class MarketTable(DataTable):
    """Table of markets with mid, spread, depth."""

    def __init__(self, aggregator: OrderBookAggregator, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._aggregator = aggregator

    def on_mount(self) -> None:
        self.add_columns("Market", "Asset", "Mid", "Spread", "Bid", "Ask")

    def refresh_rows(self) -> None:
        self.clear()
        self.add_columns("Market", "Asset", "Mid", "Spread", "Bid", "Ask")
        for (market_id, asset_id), eng in self._aggregator.engines().items():
            if not eng.has_snapshot:
                continue
            mid = eng.mid_price
            spread = eng.spread
            bb = eng.best_bid
            ba = eng.best_ask
            mid_s = f"{mid:.3f}" if mid is not None else "-"
            spread_s = f"{spread:.3f}" if spread is not None else "-"
            bb_s = f"{bb:.3f}" if bb is not None else "-"
            ba_s = f"{ba:.3f}" if ba is not None else "-"
            self.add_row(
                market_id[:16] + "..." if len(market_id) > 16 else market_id,
                asset_id[:12] + "..." if len(asset_id) > 12 else asset_id,
                mid_s,
                spread_s,
                bb_s,
                ba_s,
            )


class PredExTUI(App[None]):
    """PredExchange TUI - live orderbooks and health."""

    TITLE = "PredExchange"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, manager: IngestionManager, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._manager = manager
        self._aggregator = manager.orderbook_aggregator or OrderBookAggregator()
        if manager.orderbook_aggregator is None:
            manager.orderbook_aggregator = self._aggregator
        self._stop_event = asyncio.Event()
        self._ingestion_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield HealthPanel(id="health")
        yield MarketTable(self._aggregator, id="markets")
        yield Footer()

    def on_mount(self) -> None:
        self._ingestion_task = asyncio.create_task(self._run_ingestion())
        self.set_interval(0.5, self._refresh)

    async def _run_ingestion(self) -> None:
        await self._manager.run(stop_event=self._stop_event)

    def _refresh(self) -> None:
        status = self._manager.get_status()
        health = self.query_one(HealthPanel)
        health.status = "Connected"
        health.msg_count = status["msg_count"]
        health.msgs_per_sec = status["msgs_per_sec"]
        table = self.query_one(MarketTable)
        table.refresh_rows()

    def on_unmount(self) -> None:
        self._stop_event.set()
        if self._ingestion_task and not self._ingestion_task.done():
            self._ingestion_task.cancel()
        self._manager.close()


def run_tui(settings: Any) -> None:
    """Entry point: create manager + aggregator and run TUI."""
    from predexchange.storage.db import get_connection, init_schema
    from predexchange.storage.markets import get_tracked_asset_ids

    conn = get_connection(settings.db_path)
    init_schema(conn)
    asset_ids = get_tracked_asset_ids(conn)
    conn.close()
    if not asset_ids:
        raise SystemExit("No tracked markets. Run: predex markets discover")
    aggregator = OrderBookAggregator()
    manager = IngestionManager(
        db_path=settings.db_path,
        ws_url=settings.clob_ws_url,
        event_batch_size=settings.event_batch_size,
        reconnect_base_delay_sec=settings.reconnect_base_delay_sec,
        reconnect_max_delay_sec=settings.reconnect_max_delay_sec,
        reconnect_max_retries=settings.reconnect_max_retries,
        orderbook_aggregator=aggregator,
    )
    app = PredExTUI(manager)
    app.run()
