"""Live derived metrics from orderbook state - spread, imbalance, depth, update rate."""

from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from predexchange.orderbook.engine import OrderBookEngine


def spread_absolute(engine: OrderBookEngine) -> float | None:
    """Absolute spread (best_ask - best_bid)."""
    return engine.spread


def spread_pct(engine: OrderBookEngine) -> float | None:
    """Spread as percentage of mid."""
    mid = engine.mid_price
    sp = engine.spread
    if mid is not None and sp is not None and mid > 0:
        return (sp / mid) * 100.0
    return None


def imbalance(engine: OrderBookEngine, levels: int = 5) -> float | None:
    """Orderbook imbalance: (bid_volume - ask_volume) / (bid_volume + ask_volume) over top N levels. [-1, 1]."""
    bid_list, ask_list = engine.depth_at_levels(n=levels)
    bid_vol = sum(s for _, s in bid_list)
    ask_vol = sum(s for _, s in ask_list)
    total = bid_vol + ask_vol
    if total == 0:
        return None
    return (bid_vol - ask_vol) / total


def depth_at_levels(engine: OrderBookEngine, n: int = 5) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Top N bid and ask levels (price, size)."""
    return engine.depth_at_levels(n=n)


class MidPriceSeries:
    """Rolling mid-price history for volatility proxy and sparkline."""

    def __init__(self, maxlen: int = 100) -> None:
        self._times: deque[float] = deque(maxlen=maxlen)
        self._prices: deque[float] = deque(maxlen=maxlen)

    def push(self, ts: float, price: float) -> None:
        self._times.append(ts)
        self._prices.append(price)

    def volatility_proxy(self, window_sec: float = 60.0) -> float | None:
        """Std dev of mid price over the last window_sec seconds (if enough points)."""
        if len(self._prices) < 2:
            return None
        now = time.time()
        cutoff = now - window_sec
        prices = [p for t, p in zip(self._times, self._prices) if t >= cutoff]
        if len(prices) < 2:
            return None
        mean = sum(prices) / len(prices)
        var = sum((p - mean) ** 2 for p in prices) / (len(prices) - 1)
        return var ** 0.5

    def series(self) -> list[tuple[float, float]]:
        return list(zip(self._times, self._prices))


class UpdateRateCounter:
    """Count events per second (rolling)."""

    def __init__(self, window_sec: float = 1.0) -> None:
        self._window = window_sec
        self._times: deque[float] = deque()

    def hit(self) -> None:
        self._times.append(time.time())
        while self._times and self._times[0] < time.time() - self._window:
            self._times.popleft()

    @property
    def rate(self) -> float:
        while self._times and self._times[0] < time.time() - self._window:
            self._times.popleft()
        return len(self._times) / self._window if self._window > 0 else 0.0
