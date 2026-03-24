"""Storage + analytics helpers for whale/insider identifier."""

from __future__ import annotations

import time
from typing import Any


def upsert_ingestion_cursor(conn: Any, name: str, cursor_value: str) -> None:
    now = int(time.time() * 1000)
    conn.execute(
        """
        INSERT INTO ingestion_cursors (name, cursor_value, updated_at_ms)
        VALUES (?, ?, ?)
        ON CONFLICT (name) DO UPDATE SET cursor_value = excluded.cursor_value, updated_at_ms = excluded.updated_at_ms
        """,
        [name, cursor_value, now],
    )


def get_ingestion_cursor(conn: Any, name: str) -> str | None:
    row = conn.execute("SELECT cursor_value FROM ingestion_cursors WHERE name = ?", [name]).fetchone()
    return row[0] if row and row[0] else None


def insert_trades(conn: Any, trades: list[dict[str, Any]]) -> int:
    if not trades:
        return 0
    now = int(time.time() * 1000)
    inserted = 0
    for t in trades:
        # Best-effort dedup by transaction hash + wallet + condition + side.
        tx = t.get("transaction_hash")
        wallet = t.get("proxy_wallet")
        cond = t.get("condition_id")
        side = t.get("side")
        if tx:
            exists = conn.execute(
                """
                SELECT 1 FROM data_api_trades
                WHERE transaction_hash = ? AND proxy_wallet = ? AND condition_id = ? AND side = ?
                LIMIT 1
                """,
                [tx, wallet, cond, side],
            ).fetchone()
            if exists:
                continue
        conn.execute(
            """
            INSERT INTO data_api_trades (
                proxy_wallet, side, asset, condition_id, size, price, notional_usdc,
                timestamp_ms, title, slug, event_slug, outcome, transaction_hash, ingested_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                wallet,
                t.get("side"),
                t.get("asset"),
                cond,
                t.get("size"),
                t.get("price"),
                t.get("notional_usdc"),
                t.get("timestamp_ms"),
                t.get("title"),
                t.get("slug"),
                t.get("event_slug"),
                t.get("outcome"),
                tx,
                now,
            ],
        )
        inserted += 1
    return inserted


def list_large_trades(conn: Any, min_notional: float, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT proxy_wallet, side, condition_id, title, outcome, size, price, notional_usdc, timestamp_ms, transaction_hash
        FROM data_api_trades
        WHERE notional_usdc >= ?
        ORDER BY timestamp_ms DESC
        LIMIT ?
        """,
        [min_notional, limit],
    ).fetchall()
    keys = [
        "wallet",
        "side",
        "condition_id",
        "title",
        "outcome",
        "size",
        "price",
        "notional_usdc",
        "timestamp_ms",
        "transaction_hash",
    ]
    return [dict(zip(keys, r)) for r in rows]


def wallet_aggregates(conn: Any, min_notional: float, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        WITH base AS (
            SELECT
                proxy_wallet,
                timestamp_ms,
                notional_usdc,
                condition_id
            FROM data_api_trades
        ),
        cuts AS (
            SELECT
                CAST(epoch_ms(now()) AS BIGINT) AS now_ms,
                CAST(epoch_ms(now() - INTERVAL '1 day') AS BIGINT) AS d1_ms,
                CAST(epoch_ms(now() - INTERVAL '7 day') AS BIGINT) AS d7_ms,
                CAST(epoch_ms(now() - INTERVAL '30 day') AS BIGINT) AS d30_ms
        ),
        roll AS (
            SELECT
                b.proxy_wallet,
                SUM(CASE WHEN b.timestamp_ms >= c.d1_ms THEN b.notional_usdc ELSE 0 END) AS spend_1d,
                SUM(CASE WHEN b.timestamp_ms >= c.d7_ms THEN b.notional_usdc ELSE 0 END) AS spend_7d,
                SUM(CASE WHEN b.timestamp_ms >= c.d30_ms THEN b.notional_usdc ELSE 0 END) AS spend_30d,
                MIN(b.timestamp_ms) AS first_seen_ms,
                MAX(b.timestamp_ms) AS last_seen_ms,
                COUNT(DISTINCT DATE_TRUNC('day', to_timestamp(b.timestamp_ms / 1000.0))) AS active_days
            FROM base b
            CROSS JOIN cuts c
            GROUP BY b.proxy_wallet
        ),
        concentration AS (
            SELECT
                proxy_wallet,
                MAX(market_notional) AS top_market_notional_30d
            FROM (
                SELECT
                    b.proxy_wallet,
                    b.condition_id,
                    SUM(b.notional_usdc) AS market_notional
                FROM base b
                CROSS JOIN cuts c
                WHERE b.timestamp_ms >= c.d30_ms
                GROUP BY b.proxy_wallet, b.condition_id
            ) x
            GROUP BY proxy_wallet
        )
        SELECT
            r.proxy_wallet,
            r.spend_1d,
            r.spend_7d,
            r.spend_30d,
            r.first_seen_ms,
            r.last_seen_ms,
            r.active_days,
            COALESCE(con.top_market_notional_30d, 0) AS top_market_notional_30d
        FROM roll r
        LEFT JOIN concentration con ON con.proxy_wallet = r.proxy_wallet
        WHERE r.spend_30d >= ?
        ORDER BY r.spend_30d DESC
        LIMIT ?
        """,
        [min_notional, limit],
    ).fetchall()
    out = []
    for r in rows:
        spend_30d = float(r[3] or 0.0)
        top_market = float(r[7] or 0.0)
        out.append(
            {
                "wallet": r[0],
                "spend_1d": float(r[1] or 0.0),
                "spend_7d": float(r[2] or 0.0),
                "spend_30d": spend_30d,
                "first_seen_ms": int(r[4]) if r[4] else None,
                "last_seen_ms": int(r[5]) if r[5] else None,
                "active_days": int(r[6] or 0),
                "top_market_notional_30d": top_market,
                "top_market_concentration_30d": (top_market / spend_30d) if spend_30d > 0 else 0.0,
            }
        )
    return out


def track_wallet(conn: Any, address: str, label: str | None = None, notes: str | None = None) -> None:
    now = int(time.time() * 1000)
    conn.execute(
        """
        INSERT INTO tracked_wallets (address, label, notes, created_at_ms)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (address) DO UPDATE SET label = excluded.label, notes = excluded.notes
        """,
        [address.lower(), label, notes, now],
    )


def untrack_wallet(conn: Any, address: str) -> None:
    conn.execute("DELETE FROM tracked_wallets WHERE address = ?", [address.lower()])


def list_tracked_wallets(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT address, label, notes, created_at_ms FROM tracked_wallets ORDER BY created_at_ms DESC"
    ).fetchall()
    return [
        {"address": r[0], "label": r[1], "notes": r[2], "created_at_ms": r[3]}
        for r in rows
    ]

