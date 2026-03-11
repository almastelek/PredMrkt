"""Heuristic matching: suggest candidate Polymarket <-> Kalshi pairs by title (and optional date) similarity."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

import structlog

from predexchange.ingestion.kalshi.client import KalshiClient
from predexchange.storage.candidate_rejections import get_rejected_set
from predexchange.storage.event_pairs import list_pairs as list_event_pairs
from predexchange.storage.markets import list_markets

log = structlog.get_logger(__name__)

# Common words to drop when comparing titles (reduces noise)
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "by", "with", "will", "be", "is", "are", "was", "were", "been",
        "have", "has", "had", "do", "does", "did", "this", "that", "these",
        "those", "it", "its", "?", "yes", "no",
    }
)


def _normalize_title(s: str) -> str:
    """Lowercase, strip punctuation, collapse spaces."""
    if not s or not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _token_set(s: str) -> set[str]:
    """Normalize and return set of non-empty, non-stopword tokens."""
    norm = _normalize_title(s)
    tokens = {w for w in norm.split() if w and w not in _STOPWORDS}
    return tokens


def _title_similarity(a: str, b: str) -> float:
    """Score in [0, 1]: combination of sequence ratio and token overlap."""
    if not a or not b:
        return 0.0
    na = _normalize_title(a)
    nb = _normalize_title(b)
    if not na or not nb:
        return 0.0
    seq_ratio = SequenceMatcher(None, na, nb).ratio()
    ta, tb = _token_set(a), _token_set(b)
    if not ta and not tb:
        return seq_ratio
    if not ta or not tb:
        return 0.5 * seq_ratio
    overlap = len(ta & tb) / max(len(ta), len(tb))
    return 0.5 * seq_ratio + 0.5 * overlap


def _parse_kalshi_date(ev: dict[str, Any]) -> int | None:
    """Return Unix timestamp (seconds) for event date if available, else None."""
    # strike_date can be ISO string or seconds
    strike = ev.get("strike_date")
    if strike is None:
        strike = ev.get("close_time") or ev.get("expiration_time")
    if strike is None:
        return None
    if isinstance(strike, (int, float)):
        return int(strike) if strike > 1e10 else int(strike)  # assume seconds
    if isinstance(strike, str) and strike:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(strike.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except (ValueError, TypeError):
            pass
    return None


def suggest_candidates(
    conn: Any,
    limit: int = 50,
    min_score: float = 0.4,
    polymarket_limit: int = 500,
    kalshi_event_limit: int = 200,
) -> list[dict[str, Any]]:
    """
    Suggest candidate (Polymarket, Kalshi) pairs by title (+ optional date) similarity.
    Excludes pairs already in event_pairs or in candidate_rejections.
    Returns list of dicts: score, polymarket_market_id, polymarket_title, kalshi_event_ticker,
    kalshi_market_ticker, kalshi_title, kalshi_strike_ts (optional).
    """
    # Already approved
    approved = list_event_pairs(conn)
    approved_set = {(p["polymarket_market_id"], p["kalshi_market_ticker"]) for p in approved}
    rejected_set = get_rejected_set(conn)

    # Polymarket: from DB (venue=polymarket, has title)
    all_markets = list_markets(conn, tracked_only=False)
    pm_markets = [
        {"market_id": m["market_id"], "title": (m.get("title") or "").strip() or m["market_id"]}
        for m in all_markets
        if (m.get("venue") or "polymarket").lower() == "polymarket" and (m.get("title") or "").strip()
    ]
    pm_markets = pm_markets[:polymarket_limit]

    # Kalshi: from API
    client = KalshiClient()
    kalshi_events: list[dict[str, Any]] = []
    try:
        data = client.get_events(
            limit=kalshi_event_limit,
            status="open",
            with_nested_markets=True,
        )
        for ev in data.get("events") or []:
            event_ticker = ev.get("event_ticker") or ev.get("ticker") or ""
            title = (ev.get("title") or ev.get("subtitle") or "").strip() or event_ticker
            markets = ev.get("markets") or []
            if not markets:
                # Single-market event might have ticker on event
                ticker = ev.get("ticker") or event_ticker
                if ticker:
                    kalshi_events.append({
                        "event_ticker": event_ticker,
                        "market_ticker": ticker,
                        "title": title,
                        "strike_ts": _parse_kalshi_date(ev),
                    })
                continue
            for m in markets:
                mt = (m.get("ticker") or m.get("market_ticker") or "").strip()
                if not mt:
                    continue
                mt_title = (m.get("title") or m.get("subtitle") or "").strip() or title
                kalshi_events.append({
                    "event_ticker": event_ticker,
                    "market_ticker": mt,
                    "title": mt_title,
                    "strike_ts": _parse_kalshi_date(ev) or _parse_kalshi_date(m),
                })
    except Exception as e:
        log.warning("kalshi_events_fetch_failed", error=str(e))
        return []

    candidates: list[dict[str, Any]] = []
    for pm in pm_markets:
        for k in kalshi_events:
            key = (pm["market_id"], k["market_ticker"])
            if key in approved_set or key in rejected_set:
                continue
            score = _title_similarity(pm["title"], k["title"])
            if score < min_score:
                continue
            candidates.append({
                "score": round(score, 3),
                "polymarket_market_id": pm["market_id"],
                "polymarket_title": pm["title"],
                "kalshi_event_ticker": k["event_ticker"],
                "kalshi_market_ticker": k["market_ticker"],
                "kalshi_title": k["title"],
                "kalshi_strike_ts": k.get("strike_ts"),
            })

    candidates.sort(key=lambda x: -x["score"])
    return candidates[:limit]
