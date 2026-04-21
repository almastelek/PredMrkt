"""Storage helpers for signal episodes, stats, and alerts."""

from __future__ import annotations

import json
from typing import Any

EPISODE_COLUMNS = [
    "episode_id", "wallet", "condition_id", "outcome", "asset_id",
    "market_slug", "event_slug", "title",
    "episode_start_ms", "episode_end_ms",
    "trade_count", "buy_count", "sell_count",
    "gross_notional_usdc", "net_notional_usdc",
    "avg_fill_price", "vwap_price", "max_single_fill_usdc",
    "market_category", "mins_to_event_start", "mins_to_resolution",
    "px_t0", "px_fwd_1h", "px_fwd_6h", "px_fwd_24h",
    "ret_1h", "ret_6h", "ret_24h",
]


def _row_to_episode(r: tuple) -> dict[str, Any]:
    return {name: r[i] for i, name in enumerate(EPISODE_COLUMNS)}


def list_episodes(
    conn: Any,
    *,
    wallet: str | None = None,
    condition_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []
    if wallet:
        where.append("wallet = ?")
        params.append(wallet.lower())
    if condition_id:
        where.append("condition_id = ?")
        params.append(condition_id)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"""
        SELECT {", ".join(EPISODE_COLUMNS)}
        FROM wallet_trade_episodes
        {clause}
        ORDER BY episode_end_ms DESC
        LIMIT ?
    """
    rows = conn.execute(sql, params + [int(limit)]).fetchall()
    return [_row_to_episode(r) for r in rows]


def get_wallet_stats(conn: Any, wallet: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            wallet, asof_ms, episodes_30d, gross_notional_30d,
            concentration_top_market_30d, active_days_30d,
            hitrate_24h_90d, avg_ret_24h_90d, sharpe_like_90d,
            edge_consistency_90d, sports_share_30d, non_sports_share_30d,
            historical_episode_count
        FROM wallet_signal_stats
        WHERE wallet = ?
        """,
        [wallet.lower()],
    ).fetchone()
    if not row:
        return None
    keys = [
        "wallet", "asof_ms", "episodes_30d", "gross_notional_30d",
        "concentration_top_market_30d", "active_days_30d",
        "hitrate_24h_90d", "avg_ret_24h_90d", "sharpe_like_90d",
        "edge_consistency_90d", "sports_share_30d", "non_sports_share_30d",
        "historical_episode_count",
    ]
    return dict(zip(keys, row))


ALERT_COLUMNS = [
    "alert_id", "episode_id", "wallet", "condition_id", "market_category",
    "scored_at_ms", "base_edge_score", "context_adjusted_score",
    "insider_likelihood_score",
    "factor_timing", "factor_size", "factor_concentration",
    "factor_history", "factor_coordination", "factor_sports_penalty",
    "reason_codes_json", "review_status",
]


def list_alerts(
    conn: Any,
    *,
    min_score: float = 0.0,
    market_category: str | None = None,
    include_sports: bool = True,
    limit: int = 100,
) -> list[dict[str, Any]]:
    where = ["a.insider_likelihood_score >= ?"]
    params: list[Any] = [float(min_score)]
    if market_category:
        where.append("LOWER(COALESCE(a.market_category, '')) LIKE ?")
        params.append(f"%{market_category.lower()}%")
    if not include_sports:
        where.append("LOWER(COALESCE(a.market_category, '')) NOT LIKE '%sport%'")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"""
        SELECT {", ".join("a." + c for c in ALERT_COLUMNS)},
               e.title, e.outcome, e.gross_notional_usdc, e.episode_end_ms
        FROM wallet_signal_alerts a
        LEFT JOIN wallet_trade_episodes e ON e.episode_id = a.episode_id
        {clause}
        ORDER BY a.insider_likelihood_score DESC, a.scored_at_ms DESC
        LIMIT ?
    """
    rows = conn.execute(sql, params + [int(limit)]).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d: dict[str, Any] = {name: r[i] for i, name in enumerate(ALERT_COLUMNS)}
        d["title"] = r[len(ALERT_COLUMNS)]
        d["outcome"] = r[len(ALERT_COLUMNS) + 1]
        d["gross_notional_usdc"] = r[len(ALERT_COLUMNS) + 2]
        d["episode_end_ms"] = r[len(ALERT_COLUMNS) + 3]
        raw = d.pop("reason_codes_json") or "[]"
        try:
            d["reason_codes"] = json.loads(raw)
        except Exception:
            d["reason_codes"] = []
        out.append(d)
    return out
