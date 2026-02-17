"""Strategy protocol - venue-agnostic, replay-compatible."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol


class MarketState(Protocol):
    """Minimal market state passed to strategies."""

    @property
    def market_id(self) -> str: ...
    @property
    def asset_id(self) -> str: ...
    @property
    def best_bid(self) -> float | None: ...
    @property
    def best_ask(self) -> float | None: ...
    @property
    def mid_price(self) -> float | None: ...
    @property
    def spread(self) -> float | None: ...


class TradePrintView(Protocol):
    """Minimal trade view."""

    market_id: str
    asset_id: str
    side: str
    price: float
    size: float
    exchange_ts: int | None


class Strategy(ABC):
    """Base for strategies. Venue-agnostic, replay-compatible."""

    @abstractmethod
    def on_book_update(self, market_id: str, asset_id: str, state: MarketState) -> None:
        """Called when orderbook updates."""
        ...

    @abstractmethod
    def on_trade(self, trade: TradePrintView) -> None:
        """Called when a trade is printed."""
        ...

    def on_timer(self, timestamp: int) -> None:
        """Called periodically (e.g. every second). Optional."""
        pass
