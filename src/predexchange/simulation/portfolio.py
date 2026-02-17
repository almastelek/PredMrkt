"""Inventory and PnL tracking per strategy run."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PortfolioState:
    """Current inventory and PnL."""

    inventory: float = 0.0
    realized_pnl: float = 0.0
    cash: float = 0.0  # Cash from sells - buys (simplified)
    fill_count: int = 0

    def apply_fill(self, side: str, price: float, size: float) -> None:
        if side == "BUY":
            self.inventory += size
            self.cash -= price * size
        else:
            self.inventory -= size
            self.cash += price * size
        self.realized_pnl = self.cash + self.inventory * price  # Mark-to-market at last price
        self.fill_count += 1

    def unrealized_pnl(self, mark_price: float) -> float:
        return self.cash + self.inventory * mark_price

    def drawdown(self, peak: float) -> float:
        return peak - (self.realized_pnl + self.cash) if peak > 0 else 0.0


@dataclass
class RunResult:
    """Result of a simulation run."""

    run_id: str
    strategy_name: str
    market_id: str
    final_inventory: float
    realized_pnl: float
    fill_count: int
    events_processed: int
    params: dict = field(default_factory=dict)
