"""L2 orderbook state machine - apply snapshot/delta, track best bid/ask/mid, detect inconsistencies."""

from __future__ import annotations

from typing import Any

import structlog

from predexchange.models.orderbook import OrderBookDelta, OrderBookSnapshot, PriceLevel

log = structlog.get_logger(__name__)


class OrderBookEngine:
    """In-memory L2 orderbook per market/asset. Deterministic application of snapshot and deltas."""

    __slots__ = ("market_id", "asset_id", "bids", "asks", "_has_snapshot", "_inconsistent")

    def __init__(self, market_id: str, asset_id: str) -> None:
        self.market_id = market_id
        self.asset_id = asset_id
        # price -> size (bids: higher is better, asks: lower is better)
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self._has_snapshot = False
        self._inconsistent = False

    def apply_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        """Replace book with snapshot. Validates non-negative sizes."""
        if snapshot.market_id != self.market_id or snapshot.asset_id != self.asset_id:
            log.warning("orderbook_mismatch", expected=(self.market_id, self.asset_id), got=(snapshot.market_id, snapshot.asset_id))
            return
        self.bids = {}
        self.asks = {}
        for lev in snapshot.bids:
            if lev.size < 0:
                self._inconsistent = True
                log.warning("orderbook_negative_bid", price=lev.price, size=lev.size)
                continue
            if lev.size > 0:
                self.bids[lev.price] = lev.size
        for lev in snapshot.asks:
            if lev.size < 0:
                self._inconsistent = True
                log.warning("orderbook_negative_ask", price=lev.price, size=lev.size)
                continue
            if lev.size > 0:
                self.asks[lev.price] = lev.size
        self._has_snapshot = True
        self._inconsistent = False

    def apply_delta(self, delta: OrderBookDelta) -> None:
        """Apply a single price level update. If size is 0, remove the level."""
        if delta.market_id != self.market_id or delta.asset_id != self.asset_id:
            return
        if not self._has_snapshot:
            log.warning("orderbook_delta_before_snapshot", market_id=self.market_id, asset_id=self.asset_id)
            self._inconsistent = True
            return
        side = self.bids if delta.side == "BUY" else self.asks
        if delta.size < 0:
            self._inconsistent = True
            log.warning("orderbook_negative_delta", side=delta.side, price=delta.price, size=delta.size)
            return
        price = round(delta.price, 6)
        if delta.size == 0:
            side.pop(price, None)
        else:
            side[price] = delta.size

    @property
    def best_bid(self) -> float | None:
        return max(self.bids) if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return min(self.asks) if self.asks else None

    @property
    def mid_price(self) -> float | None:
        bb, ba = self.best_bid, self.best_ask
        if bb is not None and ba is not None:
            return (bb + ba) / 2.0
        return bb or ba

    @property
    def spread(self) -> float | None:
        bb, ba = self.best_bid, self.best_ask
        if bb is not None and ba is not None:
            return ba - bb
        return None

    @property
    def has_snapshot(self) -> bool:
        return self._has_snapshot

    @property
    def inconsistent(self) -> bool:
        return self._inconsistent

    def to_snapshot(self, exchange_ts: int | None = None, ingest_ts: int | None = None) -> OrderBookSnapshot:
        """Export current state as OrderBookSnapshot."""
        bids = [PriceLevel(price=p, size=s) for p, s in sorted(self.bids.items(), reverse=True)]
        asks = [PriceLevel(price=p, size=s) for p, s in sorted(self.asks.items())]
        return OrderBookSnapshot(
            market_id=self.market_id,
            asset_id=self.asset_id,
            bids=bids,
            asks=asks,
            exchange_ts=exchange_ts,
            ingest_ts=ingest_ts,
        )

    def depth_at_levels(self, n: int = 5) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        """Return (top N bids, top N asks) as [(price, size), ...]."""
        bid_list = sorted(self.bids.items(), reverse=True)[:n]
        ask_list = sorted(self.asks.items())[:n]
        return (bid_list, ask_list)
