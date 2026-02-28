"""Sports game state persistence (Polymarket Sports WebSocket)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from duckdb import DuckDBPyConnection


def upsert_sport_result(conn: DuckDBPyConnection, payload: dict[str, Any], updated_at: int) -> None:
    """Upsert one row into sports_games from a sport_result message."""
    game_id = payload.get("gameId")
    if game_id is None:
        return
    league = str(payload.get("leagueAbbreviation", ""))
    slug = str(payload.get("slug", ""))
    home = str(payload.get("homeTeam", ""))
    away = str(payload.get("awayTeam", ""))
    status = str(payload.get("status", ""))
    score = str(payload.get("score", "")) if payload.get("score") is not None else None
    period = str(payload.get("period", "")) if payload.get("period") is not None else None
    elapsed = str(payload.get("elapsed", "")) if payload.get("elapsed") is not None else None
    live = bool(payload.get("live", False))
    ended = bool(payload.get("ended", False))
    turn = str(payload.get("turn", "")) if payload.get("turn") is not None else None
    finished_ts = str(payload.get("finished_timestamp", "")) if payload.get("finished_timestamp") is not None else None

    conn.execute(
        """
        INSERT INTO sports_games (
            game_id, league_abbreviation, slug, home_team, away_team, status, score,
            period, elapsed, live, ended, turn, finished_timestamp, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (game_id) DO UPDATE SET
            league_abbreviation = excluded.league_abbreviation,
            slug = excluded.slug,
            home_team = excluded.home_team,
            away_team = excluded.away_team,
            status = excluded.status,
            score = excluded.score,
            period = excluded.period,
            elapsed = excluded.elapsed,
            live = excluded.live,
            ended = excluded.ended,
            turn = excluded.turn,
            finished_timestamp = excluded.finished_timestamp,
            updated_at = excluded.updated_at
        """,
        [game_id, league, slug, home, away, status, score, period, elapsed, live, ended, turn, finished_ts, updated_at],
    )


def list_sports_games(
    conn: DuckDBPyConnection,
    *,
    league: str | None = None,
    status: str | None = None,
    live_first: bool = True,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    Return games from sports_games. Optional league (e.g. nfl, nhl) and status (e.g. InProgress, Scheduled).
    If live_first, order by live DESC then ended ASC then updated_at DESC so live games are first, then upcoming, then ended.
    """
    conditions = ["1=1"]
    params: list[Any] = []
    if league:
        conditions.append("LOWER(TRIM(league_abbreviation)) = LOWER(TRIM(?))")
        params.append(league)
    if status:
        conditions.append("LOWER(TRIM(status)) = LOWER(TRIM(?))")
        params.append(status)
    where = " AND ".join(conditions)
    order = "live DESC, ended ASC, updated_at DESC" if live_first else "updated_at DESC"
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT game_id, league_abbreviation, slug, home_team, away_team, status, score,
               period, elapsed, live, ended, turn, finished_timestamp, updated_at
        FROM sports_games
        WHERE {where}
        ORDER BY {order}
        LIMIT ?
        """,
        params,
    ).fetchall()
    cols = [
        "game_id", "league_abbreviation", "slug", "home_team", "away_team", "status", "score",
        "period", "elapsed", "live", "ended", "turn", "finished_timestamp", "updated_at",
    ]
    return [dict(zip(cols, r)) for r in rows]
