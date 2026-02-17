"""Orderbook engine unit tests."""

import pytest

from predexchange.models.orderbook import OrderBookDelta, OrderBookSnapshot, PriceLevel
from predexchange.orderbook.engine import OrderBookEngine, create_orderbook_engine


def test_orderbook_snapshot_then_delta():
    eng = OrderBookEngine("m1", "a1")
    assert eng.best_bid is None
    assert eng.mid_price is None
    snap = OrderBookSnapshot(
        market_id="m1",
        asset_id="a1",
        bids=[PriceLevel(price=0.5, size=100), PriceLevel(price=0.49, size=50)],
        asks=[PriceLevel(price=0.52, size=80), PriceLevel(price=0.53, size=60)],
    )
    eng.apply_snapshot(snap)
    assert eng.best_bid == 0.5
    assert eng.best_ask == 0.52
    assert eng.mid_price == 0.51
    assert abs(eng.spread - 0.02) < 1e-9
    eng.apply_delta(OrderBookDelta(market_id="m1", asset_id="a1", side="BUY", price=0.5, size=0))
    assert eng.best_bid == 0.49
    eng.apply_delta(OrderBookDelta(market_id="m1", asset_id="a1", side="SELL", price=0.54, size=10))
    assert eng.best_ask == 0.52  # still min of asks
    assert 0.54 in eng.asks and eng.asks[0.54] == 10


def test_create_engine_returns_python_or_rust():
    eng = create_orderbook_engine("m1", "a1")
    assert hasattr(eng, "apply_snapshot")
    assert hasattr(eng, "apply_delta")
    assert hasattr(eng, "mid_price")
