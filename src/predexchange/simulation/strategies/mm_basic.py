"""Basic market-making: quote around mid with inventory skew."""

from __future__ import annotations

from predexchange.simulation.strategy import MarketState, Strategy, TradePrintView


class MMInventoryStrategy(Strategy):
    """Quote bid/ask around mid, skew by inventory. Placeholder quotes (no actual orders in sim)."""

    def __init__(self, spread_frac: float = 0.01, skew_per_unit: float = 0.001) -> None:
        self.spread_frac = spread_frac
        self.skew_per_unit = skew_per_unit
        self._inventory = 0.0
        self._quotes: list[tuple[str, float, float]] = []  # (side, price, size) for fill model

    def on_book_update(self, market_id: str, asset_id: str, state: MarketState) -> None:
        mid = state.mid_price
        if mid is None:
            return
        spread = state.spread or 0.01
        half = max(spread / 2, self.spread_frac * mid)
        skew = self._inventory * self.skew_per_unit
        bid = mid - half - skew
        ask = mid + half - skew
        bid = max(0.0, min(1.0, bid))
        ask = max(0.0, min(1.0, ask))
        self._quotes = [("BUY", bid, 10.0), ("SELL", ask, 10.0)]

    def on_trade(self, trade: TradePrintView) -> None:
        if trade.side == "BUY":
            self._inventory -= trade.size
        else:
            self._inventory += trade.size

    def get_quotes(self) -> list[tuple[str, float, float]]:
        return list(self._quotes)
