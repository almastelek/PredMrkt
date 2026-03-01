'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';
const POLL_MS = 5000;

type GameDetail = {
  game: {
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
    first_live_at: number | null;
  };
  market_id: string | null;
  asset_id: string | null;
  start_ts: number | null;
};

type SeriesPoint = { t: number; mid: number; time: string };

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

export default function SportsGameDetailPage() {
  const params = useParams();
  const gameId = params?.game_id as string;
  const [detail, setDetail] = useState<GameDetail | null>(null);
  const [series, setSeries] = useState<SeriesPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDetail = useCallback(() => {
    if (!gameId) return;
    fetch(`${API}/sports/games/${encodeURIComponent(gameId)}`)
      .then((r) => {
        if (!r.ok) {
          if (r.status === 404) throw new Error('Game not found');
          throw new Error(`API ${r.status}`);
        }
        return r.json();
      })
      .then((d: GameDetail) => {
        setDetail(d);
        setError(null);
        if (d.market_id && d.asset_id) {
          const end = Date.now();
          const start = d.start_ts && d.start_ts > 0 ? d.start_ts : end - 2 * 60 * 60 * 1000;
          const q = new URLSearchParams({
            asset_id: d.asset_id,
            start_ts: String(start),
            end_ts: String(end),
            max_points: '500',
          });
          return fetch(
            `${API}/markets/${encodeURIComponent(d.market_id)}/timeseries?${q}`
          )
            .then((r) => r.json())
            .then((res: { series?: { t: number; mid: number }[] }) => {
              const raw = res.series || [];
              setSeries(
                raw.map((p: { t: number; mid: number }) => ({
                  ...p,
                  time: new Date(p.t).toLocaleTimeString(),
                }))
              );
            })
            .catch(() => setSeries([]));
        }
        setSeries([]);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setDetail(null);
        setSeries([]);
      })
      .finally(() => setLoading(false));
  }, [gameId]);

  useEffect(() => {
    fetchDetail();
    const id = setInterval(fetchDetail, POLL_MS);
    return () => clearInterval(id);
  }, [fetchDetail]);

  if (error) {
    return (
      <div>
        <p style={{ color: '#c66' }}>{error}</p>
        <Link href="/sports" style={{ color: '#6af' }}>
          ← Back to Sports
        </Link>
      </div>
    );
  }

  if (loading && !detail) return <p>Loading…</p>;
  if (!detail) return null;

  const g = detail.game;
  const leagueLabel =
    LEAGUE_LABELS[g.league_abbreviation?.toLowerCase()] ??
    g.league_abbreviation ??
    '—';
  const lastMid =
    series.length > 0 ? series[series.length - 1]?.mid : null;

  return (
    <div style={{ maxWidth: 900 }}>
      <div style={{ marginBottom: 16 }}>
        <Link
          href="/sports"
          style={{ color: '#6af', fontSize: 14, textDecoration: 'none' }}
        >
          ← Sports
        </Link>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
          marginBottom: 24,
          padding: 16,
          background: g.live ? '#1a2a1a' : '#161616',
          border: `1px solid ${g.live ? '#2a4a2a' : '#2a2a2a'}`,
          borderRadius: 8,
        }}
      >
        <span style={{ fontSize: 12, color: '#666' }}>{leagueLabel}</span>
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
          <span style={{ fontSize: 10, color: '#6a6', marginLeft: 'auto' }}>
            LIVE
          </span>
        )}
        {g.ended && (
          <span style={{ fontSize: 10, color: '#888', marginLeft: 'auto' }}>
            Final
          </span>
        )}
        {lastMid != null && (
          <div
            style={{
              marginLeft: 'auto',
              padding: '6px 12px',
              background: '#1a2a2a',
              borderRadius: 6,
              border: '1px solid #2a4a4a',
            }}
          >
            <span style={{ color: '#888', fontSize: 11 }}>Probability</span>
            <div style={{ fontSize: 18, fontWeight: 600, color: '#7d7' }}>
              {(lastMid * 100).toFixed(1)}%
            </div>
          </div>
        )}
      </div>

      {!detail.market_id || !detail.asset_id ? (
        <p style={{ color: '#888' }}>
          No Polymarket market linked for this game. Price feed will appear here
          when a market is available for this game.
        </p>
      ) : series.length === 0 ? (
        <p style={{ color: '#888' }}>
          No price data yet. Run ingestion and wait for events, or the game may
          not have started.
        </p>
      ) : (
        <section
          style={{
            background: '#1a1a1a',
            border: '1px solid #333',
            borderRadius: 8,
            padding: 16,
          }}
        >
          <h3 style={{ marginTop: 0, marginBottom: 8 }}>
            Live price from game start
          </h3>
          <p style={{ color: '#888', fontSize: 12, marginBottom: 16 }}>
            Mid price (probability) over time. Refreshes every {POLL_MS / 1000}s.
          </p>
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ top: 8, right: 8, left: 8, bottom: 24 }}>
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 11 }}
                  stroke="#666"
                  interval="preserveStartEnd"
                />
                <YAxis
                  domain={[0, 1]}
                  tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                  tick={{ fontSize: 11 }}
                  stroke="#666"
                />
                <Tooltip
                  formatter={(v: number) => [`${(v * 100).toFixed(1)}%`, 'Prob']}
                  labelFormatter={(_, payload) =>
                    payload?.[0]?.payload?.time ?? ''
                  }
                />
                <ReferenceLine y={0.5} stroke="#444" strokeDasharray="2 2" />
                <Line
                  type="monotone"
                  dataKey="mid"
                  name="Prob"
                  stroke="#5a9"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}
    </div>
  );
}
