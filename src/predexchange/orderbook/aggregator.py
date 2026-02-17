"""Live orderbook aggregator - one engine per (market_id, asset_id), fed from raw WS messages."""

from __future__ import annotations

from typing import Any

from predexchange.ingestion.polymarket.normalize import (
    parse_book_message,
    parse_price_change_message,
)
from predexchange.orderbook.engine import OrderBookEngine


class OrderBookAggregator:
    """Holds OrderBookEngine per (market_id, asset_id), applies normalized Polymarket messages."""

    def __init__(self) -> None:
        self._engines: dict[tuple[str, str], OrderBookEngine] = {}

    def _engine(self, market_id: str, asset_id: str) -> OrderBookEngine:
        key = (market_id, asset_id)
        if key not in self._engines:
            self._engines[key] = OrderBookEngine(market_id, asset_id)
        return self._engines[key]

    def on_message(self, payload: dict[str, Any], ingest_ts: int) -> None:
        """Process a raw Polymarket WS message and apply to the appropriate engine(s)."""
        event_type = payload.get("event_type")
        if event_type == "book":
            snap = parse_book_message(payload)
            if snap:
                eng = self._engine(snap.market_id, snap.asset_id)
                snap.ingest_ts = ingest_ts
                eng.apply_snapshot(snap)
        elif event_type == "price_change":
            for delta in parse_price_change_message(payload):
                delta.ingest_ts = ingest_ts
                eng = self._engine(delta.market_id, delta.asset_id)
                eng.apply_delta(delta)

    def get_engine(self, market_id: str, asset_id: str) -> OrderBookEngine | None:
        return self._engines.get((market_id, asset_id))

    def engines(self) -> dict[tuple[str, str], OrderBookEngine]:
        return dict(self._engines)
