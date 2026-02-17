"""Experiment runner: replay + strategy + fill model + portfolio, persist results."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from predexchange.ingestion.polymarket.normalize import parse_last_trade_message
from predexchange.orderbook.aggregator import OrderBookAggregator
from predexchange.replay.engine import stream_raw_events
from predexchange.simulation.fill_model import TouchFillModel
from predexchange.simulation.portfolio import PortfolioState, RunResult
from predexchange.simulation.strategy import Strategy


def run_simulation(
    conn: Any,
    strategy: Strategy,
    market_id: str,
    asset_id: str,
    start_ts: int | None = None,
    end_ts: int | None = None,
    fill_latency_ms: int = 0,
) -> RunResult:
    """Replay events for market, drive strategy, apply touch-fill, return RunResult."""
    aggregator = OrderBookAggregator()
    fill_model = TouchFillModel(latency_ms=fill_latency_ms)
    portfolio = PortfolioState()
    events_processed = 0

    for payload, ingest_ts in stream_raw_events(conn, market_id=market_id, start_ts=start_ts, end_ts=end_ts):
        events_processed += 1
        aggregator.on_message(payload, ingest_ts)
        eng = aggregator.get_engine(market_id, asset_id)
        if eng and eng.has_snapshot:
            strategy.on_book_update(market_id, asset_id, eng)
            # Touch-fill check for MM-style strategies that expose quotes
            if hasattr(strategy, "get_quotes") and eng.mid_price is not None:
                for side, quote_price, quote_size in strategy.get_quotes():
                    fill = fill_model.check_fill(
                        side, quote_price, quote_size, eng.mid_price, ingest_ts, market_id, asset_id
                    )
                    if fill:
                        portfolio.apply_fill(fill.side, fill.price, fill.size)
        if payload.get("event_type") == "last_trade_price":
            trade = parse_last_trade_message(payload)
            if trade:
                trade.ingest_ts = ingest_ts
                strategy.on_trade(trade)

    run_id = str(uuid.uuid4())[:8]
    return RunResult(
        run_id=run_id,
        strategy_name=getattr(strategy, "__class__", type(strategy)).__name__,
        market_id=market_id,
        final_inventory=portfolio.inventory,
        realized_pnl=portfolio.realized_pnl,
        fill_count=portfolio.fill_count,
        events_processed=events_processed,
        params={},
    )


def save_run_result(conn: Any, result: RunResult) -> None:
    """Persist RunResult to sim_runs table."""
    conn.execute(
        """
        INSERT INTO sim_runs (run_id, strategy_name, market_id, params, final_inventory, realized_pnl, fill_count, events_processed, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            result.run_id,
            result.strategy_name,
            result.market_id,
            json.dumps(result.params),
            result.final_inventory,
            result.realized_pnl,
            result.fill_count,
            result.events_processed,
            int(time.time() * 1000),
        ],
    )


def get_run_result(conn: Any, run_id: str) -> RunResult | None:
    """Load RunResult by run_id."""
    row = conn.execute(
        "SELECT run_id, strategy_name, market_id, params, final_inventory, realized_pnl, fill_count, events_processed FROM sim_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    if not row:
        return None
    return RunResult(
        run_id=row[0],
        strategy_name=row[1],
        market_id=row[2],
        final_inventory=row[4],
        realized_pnl=row[5],
        fill_count=row[6],
        events_processed=row[7],
        params=json.loads(row[3]) if row[3] else {},
    )
