'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';
const POLL_MS = 5000;

type SportsGame = {
  game_id: number;
  league_abbreviation: string;
  slug: string;
  home_team: string;
  away_team: string;
  status: string;
  score: string | null;
  period: string | null;
  elapsed: string | null;
  live: boolean;
  ended: boolean;
  turn: string | null;
  finished_timestamp: string | null;
  updated_at: number;
};

const LEAGUE_LABELS: Record<string, string> = {
  nfl: 'NFL',
  nhl: 'NHL',
  nba: 'NBA',
  mlb: 'MLB',
  cfb: 'CFB',
  cs2: 'CS2',
  lol: 'LoL',
  default: 'Other',
};

function GameRow({ g }: { g: SportsGame }) {
  const leagueLabel = LEAGUE_LABELS[g.league_abbreviation?.toLowerCase()] ?? g.league_abbreviation ?? '—';
  return (
    <Link
      href={`/sports/${g.game_id}`}
      style={{ textDecoration: 'none', color: 'inherit', display: 'block', marginBottom: 6 }}
    >
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 14px',
        background: g.live ? '#1a2a1a' : '#161616',
        border: `1px solid ${g.live ? '#2a4a2a' : '#2a2a2a'}`,
        borderRadius: 6,
        cursor: 'pointer',
      }}
    >
      <span style={{ fontSize: 11, color: '#666', minWidth: 36 }}>{leagueLabel}</span>
      <span style={{ fontWeight: 600 }}>{g.away_team}</span>
      <span style={{ color: '#888' }}>@</span>
      <span style={{ fontWeight: 600 }}>{g.home_team}</span>
      {g.score != null && g.score !== '' && (
        <span style={{ color: '#dd7', marginLeft: 8 }}>{g.score}</span>
      )}
      {g.period != null && g.period !== '' && (
        <span style={{ fontSize: 12, color: '#888' }}>{g.period}</span>
      )}
      {g.elapsed != null && g.elapsed !== '' && g.live && (
        <span style={{ fontSize: 12, color: '#6a6' }}>{g.elapsed}</span>
      )}
      {g.live && (
        <span style={{ fontSize: 10, color: '#6a6', marginLeft: 'auto' }}>LIVE</span>
      )}
      {g.ended && (
        <span style={{ fontSize: 10, color: '#888', marginLeft: 'auto' }}>Final</span>
      )}
    </div>
    </Link>
  );
}

export default function SportsPage() {
  const [games, setGames] = useState<SportsGame[]>([]);
  const [leagueFilter, setLeagueFilter] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchGames = useCallback(() => {
    const params = new URLSearchParams();
    if (leagueFilter !== 'all') params.set('league', leagueFilter);
    fetch(`${API}/sports/games?${params}`)
      .then((r) => {
        if (!r.ok) throw new Error(`API ${r.status}`);
        return r.json();
      })
      .then((data: SportsGame[]) => {
        setGames(Array.isArray(data) ? data : []);
        setError(null);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setGames([]);
      })
      .finally(() => setLoading(false));
  }, [leagueFilter]);

  useEffect(() => {
    fetchGames();
    const id = setInterval(fetchGames, POLL_MS);
    return () => clearInterval(id);
  }, [fetchGames]);

  const { live, upcoming, ended } = useMemo(() => {
    const live: SportsGame[] = [];
    const upcoming: SportsGame[] = [];
    const ended: SportsGame[] = [];
    for (const g of games) {
      if (g.live && !g.ended) live.push(g);
      else if (g.ended) ended.push(g);
      else upcoming.push(g);
    }
    return { live, upcoming, ended };
  }, [games]);

  const leagues = useMemo(() => {
    const set = new Set<string>();
    games.forEach((g) => {
      const L = (g.league_abbreviation || '').trim().toLowerCase();
      if (L) set.add(L);
    });
    return Array.from(set).sort();
  }, [games]);

  if (error) {
    return (
      <div>
        <p style={{ color: '#c66' }}>{error}</p>
        <p style={{ color: '#888', fontSize: 14 }}>Start the API with sports: <code>predex api --with-ingestion</code> or <code>predex api --with-sports</code></p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 800 }}>
      <h2 style={{ marginTop: 0, marginBottom: 8 }}>Sports</h2>
      <p style={{ color: '#888', fontSize: 13, marginBottom: 16 }}>
        Live scores and game state from Polymarket Sports WebSocket. Refreshes every {POLL_MS / 1000}s.
      </p>

      {leagues.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          <button
            type="button"
            onClick={() => setLeagueFilter('all')}
            style={{
              padding: '6px 12px',
              borderRadius: 6,
              border: '1px solid #333',
              background: leagueFilter === 'all' ? '#1a3a4a' : '#1a1a1a',
              color: leagueFilter === 'all' ? '#9ee' : '#aaa',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            All
          </button>
          {leagues.map((L) => (
            <button
              key={L}
              type="button"
              onClick={() => setLeagueFilter(L)}
              style={{
                padding: '6px 12px',
                borderRadius: 6,
                border: '1px solid #333',
                background: leagueFilter === L ? '#1a3a4a' : '#1a1a1a',
                color: leagueFilter === L ? '#9ee' : '#aaa',
                cursor: 'pointer',
                fontSize: 13,
              }}
            >
              {LEAGUE_LABELS[L] ?? L.toUpperCase()}
            </button>
          ))}
        </div>
      )}

      {loading && games.length === 0 ? (
        <p>Loading…</p>
      ) : games.length === 0 ? (
        <p style={{ color: '#666' }}>No games yet. Run <code>predex api --with-ingestion</code> or <code>predex api --with-sports</code> to stream sports data.</p>
      ) : (
        <>
          {live.length > 0 && (
            <section style={{ marginBottom: 24 }}>
              <h3 style={{ marginBottom: 12, color: '#6a6' }}>Live</h3>
              {live.map((g) => (
                <GameRow key={g.game_id} g={g} />
              ))}
            </section>
          )}
          {upcoming.length > 0 && (
            <section style={{ marginBottom: 24 }}>
              <h3 style={{ marginBottom: 12, color: '#888' }}>Upcoming</h3>
              {upcoming.map((g) => (
                <GameRow key={g.game_id} g={g} />
              ))}
            </section>
          )}
          {ended.length > 0 && (
            <section>
              <h3 style={{ marginBottom: 12, color: '#666' }}>Ended</h3>
              {ended.slice(0, 30).map((g) => (
                <GameRow key={g.game_id} g={g} />
              ))}
              {ended.length > 30 && <p style={{ color: '#666', fontSize: 12 }}>+{ended.length - 30} more</p>}
            </section>
          )}
        </>
      )}
    </div>
  );
}
