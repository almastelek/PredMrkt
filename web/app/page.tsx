'use client';

import { useCallback, useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';
const POLL_MS = 10000;

export default function Home() {
  const [health, setHealth] = useState<{ status?: string } | null>(null);
  const [stats, setStats] = useState<{
    total_events?: number;
    min_ingest_ts?: number;
    max_ingest_ts?: number;
    by_market?: { market_id: string; count: number }[];
  } | null>(null);
  const [eventsByMarket, setEventsByMarket] = useState<{ market_id: string; event_count: number; title?: string | null }[]>([]);

  const fetchData = useCallback(() => {
    fetch(`${API}/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ status: 'error' }));
    fetch(`${API}/events/stats`)
      .then((r) => r.json())
      .then(setStats)
      .catch(() => setStats(null));
    fetch(`${API}/events/by_market?limit=15`)
      .then((r) => r.json())
      .then(setEventsByMarket)
      .catch(() => setEventsByMarket([]));
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, POLL_MS);
    return () => clearInterval(id);
  }, [fetchData]);

  const barData = (eventsByMarket || []).map((m) => {
    const hasTitle = !!(m.title && m.title.trim());
    const label = hasTitle ? (m.title || '').trim() : m.market_id;
    const shortLabel = label.length > 36 ? label.slice(0, 33) + '…' : label;
    return {
      name: shortLabel,
      fullName: label,
      fullId: m.market_id,
      hasTitle,
      count: m.event_count,
    };
  });

  const apiDown = health?.status === 'error';

  return (
    <div>
      {apiDown && (
        <div style={{ background: '#3a2020', border: '1px solid #a44', padding: 12, marginBottom: 16, borderRadius: 4 }}>
          <strong>API not running.</strong> From project root run: <code style={{ background: '#222', padding: '2px 6px' }}>predex api</code> or <code style={{ background: '#222', padding: '2px 6px' }}>predex api --with-ingestion</code> (API + live data in one process)
          <br />
          <span style={{ color: '#888', fontSize: 14 }}>Dashboard talks to {API}</span>
        </div>
      )}
      <p>Status: {health?.status ?? 'loading...'} (refreshes every {POLL_MS / 1000}s)</p>
      <p>Total events in log: {stats?.total_events ?? '-'}</p>
      {stats?.min_ingest_ts != null && stats?.max_ingest_ts != null && (
        <p>Time range: {new Date(stats.min_ingest_ts).toISOString()} → {new Date(stats.max_ingest_ts).toISOString()}</p>
      )}
      <h2 style={{ marginTop: 24 }}>Event count by market (top 15)</h2>
      <p style={{ color: '#888', fontSize: 14 }}>Relative activity across markets</p>
      {barData.length > 0 ? (
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={barData} margin={{ top: 8, right: 8, left: 8, bottom: 60 }}>
            <XAxis dataKey="name" angle={-45} textAnchor="end" height={60} stroke="#888" />
            <YAxis stroke="#888" />
            <Tooltip
              content={({ payload }) =>
                payload?.[0] ? (
                  (() => {
                    const p = payload[0].payload as { fullName: string; fullId: string; hasTitle: boolean; count: number };
                    return (
                      <div style={{ background: '#222', padding: 8, border: '1px solid #444', maxWidth: 360 }}>
                        <div style={{ marginBottom: 4 }}>{p.fullName}</div>
                        {p.hasTitle && <div style={{ color: '#888', fontSize: 12 }}>{p.fullId}</div>}
                        <div style={{ marginTop: 4 }}>Events: {p.count}</div>
                        <a href={`/markets/${encodeURIComponent(p.fullId)}`} style={{ display: 'inline-block', marginTop: 8, color: '#7dd' }}>Open market detail →</a>
                      </div>
                    );
                  })()
                ) : null
              }
            />
            <Bar
              dataKey="count"
              radius={[4, 4, 0, 0]}
              cursor="pointer"
              onClick={(data: { fullId?: string }) => {
                if (data?.fullId) window.location.href = `/markets/${encodeURIComponent(data.fullId)}`;
              }}
            >
              {barData.map((_, i) => (
                <Cell key={i} fill={`hsl(${200 + i * 20}, 60%, 45%)`} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <p style={{ color: '#666' }}>No event data yet. Run ingestion: predex track start</p>
      )}
    </div>
  );
}
