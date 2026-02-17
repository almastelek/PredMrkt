"""Replay determinism and golden test."""

import json
import tempfile
from pathlib import Path

import pytest

from predexchange.replay.engine import replay_to_mid_series, stream_raw_events
from predexchange.storage.db import get_connection, init_schema
from predexchange.storage.event_log import append_raw_event, prepare_polymarket_row


@pytest.fixture
def temp_db():
    tmp = tempfile.mkdtemp()
    path = Path(tmp) / "test.duckdb"
    conn = get_connection(path)
    init_schema(conn)
    yield conn
    conn.close()
    path.unlink(missing_ok=True)
    Path(tmp).rmdir()


def test_replay_determinism(temp_db):
    """Same log + same params -> identical mid series (golden test)."""
    # Insert two book snapshots and a price_change for one market/asset
    market_id = "0xabc"
    asset_id = "123"
    book1 = {
        "event_type": "book",
        "market": market_id,
        "asset_id": asset_id,
        "bids": [{"price": "0.4", "size": "100"}, {"price": "0.39", "size": "50"}],
        "asks": [{"price": "0.42", "size": "80"}, {"price": "0.43", "size": "60"}],
        "timestamp": "1000",
    }
    book2 = {
        "event_type": "book",
        "market": market_id,
        "asset_id": asset_id,
        "bids": [{"price": "0.41", "size": "90"}, {"price": "0.40", "size": "100"}],
        "asks": [{"price": "0.43", "size": "70"}, {"price": "0.44", "size": "50"}],
        "timestamp": "2000",
    }
    for payload, ingest_ts in [(book1, 100), (book2, 200)]:
        row = prepare_polymarket_row(payload, ingest_ts)
        temp_db.execute(
            "INSERT INTO raw_events (venue, channel, event_type, market_id, asset_id, exchange_ts, ingest_ts, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            list(row),
        )

    series1 = replay_to_mid_series(temp_db, market_id, asset_id)
    series2 = replay_to_mid_series(temp_db, market_id, asset_id)
    assert series1 == series2
    assert len(series1) == 2
    # After book1 mid = (0.4+0.42)/2 = 0.41; after book2 mid = (0.41+0.43)/2 = 0.42
    assert series1[0][0] == 100
    assert series1[1][0] == 200
    assert abs((series1[0][1] or 0) - 0.41) < 0.001
    assert abs((series1[1][1] or 0) - 0.42) < 0.001
