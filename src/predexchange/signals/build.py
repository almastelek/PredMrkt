"""
Episode builder, wallet signal stats, and alert scoring.

Pipeline (idempotent; safe to re-run):
  1. build_episodes:      group data_api_trades into wallet*outcome bursts.
  2. attach_market_meta:  join markets.category for each episode.
  3. compute_forward_returns: fill px_t0 / px_fwd_* / ret_* using orderbook_snapshots
                              when we have coverage for that (condition_id, asset_id).
  4. build_wallet_stats:  rolling wallet metrics (30d flow, 90d hit-rate / Sharpe-like,
                          sports vs non-sports share) feeding the "history" factor.
  5. score_alerts:        compute factors -> base -> context-adjusted ->
                          insider-likelihood score per episode, upsert alerts.
"""

from __future__ import annotations

import json
import math
import time
from typing import Any

import structlog

log = structlog.get_logger(__name__)


# ----- Tunables (kept in code, easy to promote to config/default.toml later) -----
EPISODE_GAP_MS_DEFAULT = 30 * 60 * 1000  # 30 min gap closes an episode
EPISODE_LOOKBACK_DAYS_DEFAULT = 60
WALLET_STATS_WINDOW_30D_MS = 30 * 24 * 3600 * 1000
WALLET_STATS_WINDOW_90D_MS = 90 * 24 * 3600 * 1000
FWD_RETURN_WINDOW_MS = 30 * 60 * 1000  # +/- 30 min around target horizon

# Scoring weights (logistic combine) -- interpretable v1.
W_TIMING = 0.30
W_SIZE = 0.20
W_CONCENTRATION = 0.15
W_HISTORY = 0.25
W_COORDINATION = 0.10
W_BIAS = -0.5  # shift so "average" episode ~ low score

# Context multipliers.
SPORTS_MARKET_MULT = 0.70

# Score thresholds for reason codes.
REASON_LARGE_NOTIONAL = 50_000.0
REASON_CONCENTRATION = 0.6
REASON_HITRATE = 0.55
REASON_COORDINATION_COUNT = 2


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ------------------------------------------------------------------------------
# 1) Episode builder
# ------------------------------------------------------------------------------


def build_episodes(
    conn: Any,
    *,
    lookback_days: int = EPISODE_LOOKBACK_DAYS_DEFAULT,
    gap_ms: int = EPISODE_GAP_MS_DEFAULT,
) -> int:
    """Build/refresh wallet_trade_episodes from data_api_trades.

    Episodes are contiguous bursts of fills by the same wallet on the same
    (condition_id, outcome), separated by gaps greater than ``gap_ms``.
    Deterministic episode_id = md5(wallet|condition_id|outcome|start_ms).
    """
    now_ms = int(time.time() * 1000)
    cutoff_ms = int(now_ms - int(lookback_days) * 24 * 3600 * 1000)
    gap_ms_int = int(gap_ms)

    # NOTE: DuckDB disallows parameters inside CREATE VIEW; the two ints below are
    # server-computed from trusted inputs and inlined.
    conn.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW _sig_tagged AS
        WITH tagged AS (
            SELECT
                proxy_wallet,
                condition_id,
                outcome,
                asset,
                side,
                size,
                price,
                notional_usdc,
                timestamp_ms,
                slug,
                event_slug,
                title,
                LAG(timestamp_ms) OVER (
                    PARTITION BY proxy_wallet, condition_id, outcome
                    ORDER BY timestamp_ms
                ) AS prev_ts
            FROM data_api_trades
            WHERE timestamp_ms >= {cutoff_ms}
              AND proxy_wallet IS NOT NULL
              AND condition_id IS NOT NULL
        )
        SELECT
            *,
            SUM(CASE WHEN prev_ts IS NULL OR (timestamp_ms - prev_ts) > {gap_ms_int} THEN 1 ELSE 0 END)
                OVER (
                    PARTITION BY proxy_wallet, condition_id, outcome
                    ORDER BY timestamp_ms
                    ROWS UNBOUNDED PRECEDING
                ) AS session_seq
        FROM tagged
        """
    )

    rows = conn.execute(
        """
        WITH agg AS (
            SELECT
                proxy_wallet AS wallet,
                condition_id,
                outcome,
                session_seq,
                ANY_VALUE(asset) AS asset_id,
                ANY_VALUE(slug) AS market_slug,
                ANY_VALUE(event_slug) AS event_slug,
                ANY_VALUE(title) AS title,
                MIN(timestamp_ms) AS episode_start_ms,
                MAX(timestamp_ms) AS episode_end_ms,
                COUNT(*) AS trade_count,
                SUM(CASE WHEN UPPER(COALESCE(side, '')) = 'BUY' THEN 1 ELSE 0 END) AS buy_count,
                SUM(CASE WHEN UPPER(COALESCE(side, '')) = 'SELL' THEN 1 ELSE 0 END) AS sell_count,
                SUM(COALESCE(notional_usdc, 0)) AS gross_notional,
                SUM(
                    CASE
                        WHEN UPPER(COALESCE(side, '')) = 'BUY' THEN COALESCE(notional_usdc, 0)
                        WHEN UPPER(COALESCE(side, '')) = 'SELL' THEN -COALESCE(notional_usdc, 0)
                        ELSE 0
                    END
                ) AS net_notional,
                AVG(price) AS avg_price,
                CASE WHEN SUM(size) > 0 THEN SUM(notional_usdc) / SUM(size) END AS vwap_price,
                MAX(COALESCE(notional_usdc, 0)) AS max_single_fill
            FROM _sig_tagged
            GROUP BY proxy_wallet, condition_id, outcome, session_seq
        )
        SELECT
            md5(
                COALESCE(wallet, '') || '|' ||
                COALESCE(condition_id, '') || '|' ||
                COALESCE(outcome, '') || '|' ||
                CAST(episode_start_ms AS VARCHAR)
            ) AS episode_id,
            wallet, condition_id, outcome, asset_id, market_slug, event_slug, title,
            episode_start_ms, episode_end_ms, trade_count, buy_count, sell_count,
            gross_notional, net_notional, avg_price, vwap_price, max_single_fill
        FROM agg
        """
    ).fetchall()

    upserted = 0
    for r in rows:
        (
            episode_id, wallet, condition_id, outcome, asset_id,
            market_slug, event_slug, title,
            episode_start_ms, episode_end_ms, trade_count, buy_count, sell_count,
            gross_notional, net_notional, avg_price, vwap_price, max_single_fill,
        ) = r
        conn.execute(
            """
            INSERT INTO wallet_trade_episodes (
                episode_id, wallet, condition_id, outcome, asset_id,
                market_slug, event_slug, title,
                episode_start_ms, episode_end_ms,
                trade_count, buy_count, sell_count,
                gross_notional_usdc, net_notional_usdc,
                avg_fill_price, vwap_price, max_single_fill_usdc,
                created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (episode_id) DO UPDATE SET
                episode_end_ms = excluded.episode_end_ms,
                trade_count = excluded.trade_count,
                buy_count = excluded.buy_count,
                sell_count = excluded.sell_count,
                gross_notional_usdc = excluded.gross_notional_usdc,
                net_notional_usdc = excluded.net_notional_usdc,
                avg_fill_price = excluded.avg_fill_price,
                vwap_price = excluded.vwap_price,
                max_single_fill_usdc = excluded.max_single_fill_usdc,
                asset_id = excluded.asset_id,
                market_slug = excluded.market_slug,
                event_slug = excluded.event_slug,
                title = excluded.title,
                updated_at_ms = excluded.updated_at_ms
            """,
            [
                episode_id, wallet, condition_id, outcome, asset_id,
                market_slug, event_slug, title,
                int(episode_start_ms), int(episode_end_ms),
                int(trade_count or 0), int(buy_count or 0), int(sell_count or 0),
                float(gross_notional or 0.0), float(net_notional or 0.0),
                float(avg_price) if avg_price is not None else None,
                float(vwap_price) if vwap_price is not None else None,
                float(max_single_fill or 0.0),
                now_ms, now_ms,
            ],
        )
        upserted += 1

    log.info("signals_build_episodes", upserted=upserted, lookback_days=lookback_days)
    return upserted


# ------------------------------------------------------------------------------
# 2) Attach market metadata (category -> sports detection)
# ------------------------------------------------------------------------------


def attach_market_meta(conn: Any) -> int:
    res = conn.execute(
        """
        UPDATE wallet_trade_episodes AS e
        SET market_category = m.category
        FROM markets AS m
        WHERE m.market_id = e.condition_id
          AND (e.market_category IS DISTINCT FROM m.category)
        """
    )
    # DuckDB UPDATE returns rowcount via .fetchone() on cursor for some versions.
    try:
        n = res.fetchone()[0] if res and res.description else 0
    except Exception:
        n = 0
    log.info("signals_attach_market_meta", updated=n)
    return int(n or 0)


# ------------------------------------------------------------------------------
# 3) Forward returns (best-effort, uses orderbook_snapshots when available)
# ------------------------------------------------------------------------------


def _lookup_mid(
    conn: Any,
    market_id: str | None,
    asset_id: str | None,
    target_ts_ms: int,
    *,
    direction: str = "before",
    window_ms: int = FWD_RETURN_WINDOW_MS,
) -> float | None:
    """Pick the closest orderbook mid to target_ts within window.

    direction="before" -> latest mid <= target (used for px_t0)
    direction="after"  -> first mid >= target (used for px_fwd)
    """
    if not market_id or not asset_id:
        return None
    if direction == "before":
        row = conn.execute(
            """
            SELECT mid_price
            FROM orderbook_snapshots
            WHERE market_id = ? AND asset_id = ?
              AND timestamp <= ? AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            [market_id, asset_id, int(target_ts_ms), int(target_ts_ms - window_ms)],
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT mid_price
            FROM orderbook_snapshots
            WHERE market_id = ? AND asset_id = ?
              AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
            LIMIT 1
            """,
            [market_id, asset_id, int(target_ts_ms), int(target_ts_ms + window_ms)],
        ).fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0])


def compute_forward_returns(conn: Any, *, limit: int = 500) -> int:
    """Fill px_t0 and forward prices/returns for episodes that have none yet."""
    rows = conn.execute(
        """
        SELECT episode_id, condition_id, asset_id, episode_end_ms,
               net_notional_usdc, avg_fill_price
        FROM wallet_trade_episodes
        WHERE px_t0 IS NULL
        ORDER BY episode_end_ms DESC
        LIMIT ?
        """,
        [int(limit)],
    ).fetchall()

    if not rows:
        return 0

    now_ms = int(time.time() * 1000)
    updated = 0
    for r in rows:
        episode_id, condition_id, asset_id, end_ms, net_notional, avg_fill = r
        px_t0 = _lookup_mid(conn, condition_id, asset_id, int(end_ms), direction="before")
        if px_t0 is None and avg_fill is not None:
            px_t0 = float(avg_fill)

        def _fwd(h_hours: float) -> float | None:
            return _lookup_mid(
                conn, condition_id, asset_id,
                int(end_ms) + int(h_hours * 3600 * 1000),
                direction="after",
            )

        px1 = _fwd(1)
        px6 = _fwd(6)
        px24 = _fwd(24)

        sign = 1.0 if (net_notional or 0.0) >= 0 else -1.0

        def _ret(fwd: float | None) -> float | None:
            if px_t0 is None or fwd is None or px_t0 == 0:
                return None
            return sign * (fwd - px_t0) / px_t0

        conn.execute(
            """
            UPDATE wallet_trade_episodes
            SET px_t0 = ?,
                px_fwd_1h = ?,
                px_fwd_6h = ?,
                px_fwd_24h = ?,
                ret_1h = ?,
                ret_6h = ?,
                ret_24h = ?,
                updated_at_ms = ?
            WHERE episode_id = ?
            """,
            [
                px_t0, px1, px6, px24,
                _ret(px1), _ret(px6), _ret(px24),
                now_ms, episode_id,
            ],
        )
        updated += 1

    log.info("signals_forward_returns", updated=updated)
    return updated


# ------------------------------------------------------------------------------
# 4) Wallet signal stats
# ------------------------------------------------------------------------------


def build_wallet_stats(conn: Any) -> int:
    now_ms = int(time.time() * 1000)
    d30 = now_ms - WALLET_STATS_WINDOW_30D_MS
    d90 = now_ms - WALLET_STATS_WINDOW_90D_MS

    d30_i = int(d30)
    d90_i = int(d90)
    conn.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW _sig_stats AS
        WITH recent AS (
            SELECT *
            FROM wallet_trade_episodes
            WHERE episode_end_ms >= {d90_i}
        ),
        rolls AS (
            SELECT
                wallet,
                SUM(CASE WHEN episode_end_ms >= {d30_i} THEN gross_notional_usdc ELSE 0 END)
                    AS gross_notional_30d,
                SUM(CASE WHEN episode_end_ms >= {d30_i} THEN 1 ELSE 0 END) AS episodes_30d,
                COUNT(*) AS historical_episode_count,
                COUNT(DISTINCT DATE_TRUNC('day', to_timestamp(episode_end_ms / 1000.0)))
                    FILTER (WHERE episode_end_ms >= {d30_i}) AS active_days_30d,
                AVG(CASE WHEN ret_24h IS NOT NULL THEN (CASE WHEN ret_24h > 0 THEN 1.0 ELSE 0.0 END) END)
                    AS hitrate_24h_90d,
                AVG(ret_24h) FILTER (WHERE ret_24h IS NOT NULL) AS avg_ret_24h_90d,
                STDDEV(ret_24h) FILTER (WHERE ret_24h IS NOT NULL) AS std_ret_24h_90d
            FROM recent
            GROUP BY wallet
        ),
        concentration AS (
            SELECT
                wallet,
                MAX(market_notional) / NULLIF(SUM(market_notional), 0) AS concentration_top_market_30d
            FROM (
                SELECT wallet, condition_id, SUM(gross_notional_usdc) AS market_notional
                FROM recent
                WHERE episode_end_ms >= {d30_i}
                GROUP BY wallet, condition_id
            ) x
            GROUP BY wallet
        ),
        sports AS (
            SELECT
                wallet,
                SUM(CASE WHEN LOWER(COALESCE(market_category, '')) LIKE '%sport%'
                         THEN gross_notional_usdc ELSE 0 END) AS sports_notional_30d,
                SUM(gross_notional_usdc) AS total_notional_30d
            FROM recent
            WHERE episode_end_ms >= {d30_i}
            GROUP BY wallet
        )
        SELECT
            r.wallet,
            r.episodes_30d,
            r.gross_notional_30d,
            COALESCE(c.concentration_top_market_30d, 0) AS concentration_top_market_30d,
            r.active_days_30d,
            r.hitrate_24h_90d,
            r.avg_ret_24h_90d,
            CASE WHEN r.std_ret_24h_90d IS NULL OR r.std_ret_24h_90d = 0 THEN NULL
                 ELSE r.avg_ret_24h_90d / r.std_ret_24h_90d END AS sharpe_like_90d,
            r.std_ret_24h_90d,
            COALESCE(s.sports_notional_30d / NULLIF(s.total_notional_30d, 0), 0) AS sports_share_30d,
            COALESCE(1.0 - (s.sports_notional_30d / NULLIF(s.total_notional_30d, 0)), 1.0)
                AS non_sports_share_30d,
            r.historical_episode_count
        FROM rolls r
        LEFT JOIN concentration c ON c.wallet = r.wallet
        LEFT JOIN sports s ON s.wallet = r.wallet
        """
    )

    rows = conn.execute("SELECT * FROM _sig_stats").fetchall()
    count = 0
    for r in rows:
        (wallet, episodes_30d, gross_notional_30d, concentration,
         active_days_30d, hitrate, avg_ret, sharpe_like, std_ret,
         sports_share, non_sports_share, hist_count) = r

        # edge_consistency: favor positive avg_ret with low variance; 0 if insufficient data.
        edge_consistency = None
        if avg_ret is not None and std_ret is not None and std_ret > 0 and (hist_count or 0) >= 3:
            edge_consistency = _clip(float(avg_ret) / (float(std_ret) + 1e-9), -2.0, 2.0)

        conn.execute(
            """
            INSERT INTO wallet_signal_stats (
                wallet, asof_ms, episodes_30d, gross_notional_30d,
                concentration_top_market_30d, active_days_30d,
                hitrate_24h_90d, avg_ret_24h_90d, sharpe_like_90d,
                edge_consistency_90d, sports_share_30d, non_sports_share_30d,
                historical_episode_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (wallet) DO UPDATE SET
                asof_ms = excluded.asof_ms,
                episodes_30d = excluded.episodes_30d,
                gross_notional_30d = excluded.gross_notional_30d,
                concentration_top_market_30d = excluded.concentration_top_market_30d,
                active_days_30d = excluded.active_days_30d,
                hitrate_24h_90d = excluded.hitrate_24h_90d,
                avg_ret_24h_90d = excluded.avg_ret_24h_90d,
                sharpe_like_90d = excluded.sharpe_like_90d,
                edge_consistency_90d = excluded.edge_consistency_90d,
                sports_share_30d = excluded.sports_share_30d,
                non_sports_share_30d = excluded.non_sports_share_30d,
                historical_episode_count = excluded.historical_episode_count
            """,
            [
                wallet, now_ms,
                int(episodes_30d or 0), float(gross_notional_30d or 0.0),
                float(concentration or 0.0), int(active_days_30d or 0),
                float(hitrate) if hitrate is not None else None,
                float(avg_ret) if avg_ret is not None else None,
                float(sharpe_like) if sharpe_like is not None else None,
                edge_consistency,
                float(sports_share or 0.0),
                float(non_sports_share if non_sports_share is not None else 1.0),
                int(hist_count or 0),
            ],
        )
        count += 1

    log.info("signals_build_wallet_stats", wallets=count)
    return count


# ------------------------------------------------------------------------------
# 5) Alert scoring (explicit factors -> base -> adjusted -> insider-likelihood)
# ------------------------------------------------------------------------------


def _factor_size(gross_notional: float) -> float:
    if gross_notional <= 0:
        return -2.0
    return _clip(math.log10(gross_notional / 10_000.0), -2.0, 3.0)


def _factor_timing(mins_to_event_start: float | None, mins_to_resolution: float | None,
                   episode_end_ms: int, now_ms: int) -> float:
    # Prefer event-start/resolution timing when available.
    if mins_to_event_start is not None and mins_to_event_start > 0:
        return _clip(math.log10(max(1.0, 60.0 / mins_to_event_start)), -1.0, 2.0)
    if mins_to_resolution is not None and mins_to_resolution > 0:
        return _clip(math.log10(max(1.0, 60.0 / mins_to_resolution)), -1.0, 2.0)
    # Fallback: very mild recency weighting (events in last hour slightly favored).
    hours_ago = max(0.0, (now_ms - int(episode_end_ms)) / (3600 * 1000))
    if hours_ago < 1:
        return 0.3
    if hours_ago < 6:
        return 0.0
    if hours_ago < 24:
        return -0.2
    return -0.5


def _factor_concentration(concentration: float | None) -> float:
    if concentration is None:
        return 0.0
    return _clip((float(concentration) - 0.33) * 3.0, -1.0, 2.0)


def _factor_history(hitrate: float | None, avg_ret: float | None,
                    hist_count: int | None) -> float:
    if not hist_count or hist_count < 3:
        return 0.0
    hr = float(hitrate) if hitrate is not None else 0.5
    ar = float(avg_ret) if avg_ret is not None else 0.0
    return _clip((hr - 0.5) * 3.0 + _clip(ar * 10.0, -1.0, 1.0), -2.0, 2.0)


def _count_coordinated(
    conn: Any,
    wallet: str,
    condition_id: str,
    outcome: str | None,
    start_ms: int,
    window_ms: int = 15 * 60 * 1000,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT wallet)
        FROM wallet_trade_episodes
        WHERE condition_id = ?
          AND COALESCE(outcome, '') = COALESCE(?, '')
          AND wallet <> ?
          AND episode_start_ms BETWEEN ? AND ?
        """,
        [condition_id, outcome, wallet, int(start_ms - window_ms), int(start_ms + window_ms)],
    ).fetchone()
    return int(row[0] or 0) if row else 0


def _factor_coordination(other_wallets: int) -> float:
    if other_wallets <= 0:
        return -0.2
    return _clip(math.log2(1 + other_wallets) - 0.5, -0.5, 2.0)


def score_alerts(conn: Any, *, since_hours: int = 24 * 7, max_alerts: int = 1000) -> int:
    """Score recent episodes and upsert into wallet_signal_alerts."""
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - int(since_hours) * 3600 * 1000

    episodes = conn.execute(
        """
        SELECT
            e.episode_id, e.wallet, e.condition_id, e.outcome,
            e.episode_start_ms, e.episode_end_ms,
            e.gross_notional_usdc, e.net_notional_usdc,
            e.mins_to_event_start, e.mins_to_resolution,
            LOWER(COALESCE(e.market_category, '')) AS market_category,
            s.concentration_top_market_30d,
            s.hitrate_24h_90d, s.avg_ret_24h_90d,
            s.historical_episode_count
        FROM wallet_trade_episodes e
        LEFT JOIN wallet_signal_stats s ON s.wallet = e.wallet
        WHERE e.episode_end_ms >= ?
        ORDER BY e.episode_end_ms DESC
        LIMIT ?
        """,
        [since_ms, int(max_alerts)],
    ).fetchall()

    scored = 0
    for row in episodes:
        (episode_id, wallet, condition_id, outcome,
         start_ms, end_ms,
         gross, net,
         mins_to_event, mins_to_res,
         mkt_category,
         concentration,
         hitrate, avg_ret,
         hist_count) = row

        f_size = _factor_size(float(gross or 0.0))
        f_time = _factor_timing(mins_to_event, mins_to_res, int(end_ms), now_ms)
        f_conc = _factor_concentration(concentration)
        f_hist = _factor_history(hitrate, avg_ret, hist_count)
        others = _count_coordinated(conn, wallet, condition_id, outcome, int(start_ms))
        f_coord = _factor_coordination(others)

        z = (
            W_TIMING * f_time
            + W_SIZE * f_size
            + W_CONCENTRATION * f_conc
            + W_HISTORY * f_hist
            + W_COORDINATION * f_coord
            + W_BIAS
        )
        base = 100.0 * _sigmoid(z)

        is_sports = "sport" in (mkt_category or "")
        m_market = SPORTS_MARKET_MULT if is_sports else 1.0
        m_horizon = 1.0
        if mins_to_res is not None and mins_to_res > 0:
            if mins_to_res < 60:
                m_horizon = 0.75
            elif mins_to_res < 240:
                m_horizon = 0.9

        adjusted = base * m_market * m_horizon
        insider = min(100.0, adjusted)
        sports_penalty = base - adjusted if is_sports else 0.0

        reasons: list[str] = []
        if (gross or 0.0) >= REASON_LARGE_NOTIONAL:
            reasons.append("LARGE_NOTIONAL")
        if concentration is not None and float(concentration) >= REASON_CONCENTRATION:
            reasons.append("HIGH_CONCENTRATION")
        if hitrate is not None and float(hitrate) >= REASON_HITRATE and (hist_count or 0) >= 5:
            reasons.append("HIGH_HISTORICAL_EDGE")
        if others >= REASON_COORDINATION_COUNT:
            reasons.append("COORDINATED_ENTRY")
        if mins_to_event is not None and 0 < float(mins_to_event) < 120:
            reasons.append("PRE_EVENT_ENTRY")
        if is_sports:
            reasons.append("SPORTS_MARKET")

        alert_id = f"{episode_id}"  # one alert per episode (latest score wins)
        conn.execute(
            """
            INSERT INTO wallet_signal_alerts (
                alert_id, episode_id, wallet, condition_id, market_category,
                scored_at_ms, base_edge_score, context_adjusted_score,
                insider_likelihood_score,
                factor_timing, factor_size, factor_concentration,
                factor_history, factor_coordination, factor_sports_penalty,
                reason_codes_json, review_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
            ON CONFLICT (alert_id) DO UPDATE SET
                scored_at_ms = excluded.scored_at_ms,
                base_edge_score = excluded.base_edge_score,
                context_adjusted_score = excluded.context_adjusted_score,
                insider_likelihood_score = excluded.insider_likelihood_score,
                factor_timing = excluded.factor_timing,
                factor_size = excluded.factor_size,
                factor_concentration = excluded.factor_concentration,
                factor_history = excluded.factor_history,
                factor_coordination = excluded.factor_coordination,
                factor_sports_penalty = excluded.factor_sports_penalty,
                reason_codes_json = excluded.reason_codes_json,
                market_category = excluded.market_category
            """,
            [
                alert_id, episode_id, wallet, condition_id, mkt_category,
                now_ms, base, adjusted, insider,
                f_time, f_size, f_conc, f_hist, f_coord, sports_penalty,
                json.dumps(reasons),
            ],
        )
        scored += 1

    log.info("signals_score_alerts", scored=scored, since_hours=since_hours)
    return scored


# ------------------------------------------------------------------------------
# Orchestrator
# ------------------------------------------------------------------------------


def run_signals_pipeline(
    conn: Any,
    *,
    lookback_days: int = EPISODE_LOOKBACK_DAYS_DEFAULT,
    gap_ms: int = EPISODE_GAP_MS_DEFAULT,
    score_since_hours: int = 24 * 7,
    max_alerts: int = 1000,
    forward_returns_limit: int = 500,
) -> dict[str, int]:
    stats: dict[str, int] = {}
    stats["episodes_upserted"] = build_episodes(
        conn, lookback_days=lookback_days, gap_ms=gap_ms
    )
    stats["market_meta_updated"] = attach_market_meta(conn)
    stats["forward_returns_filled"] = compute_forward_returns(
        conn, limit=forward_returns_limit
    )
    stats["wallet_stats_upserted"] = build_wallet_stats(conn)
    stats["alerts_scored"] = score_alerts(
        conn, since_hours=score_since_hours, max_alerts=max_alerts
    )
    return stats
