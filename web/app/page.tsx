'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';
const POLL_MS = 10000;
const DEFAULT_LIMIT = 40;

type EventRow = {
  market_id: string;
  event_count: number;
  title?: string | null;
  category?: string | null;
  sparkline?: number[];
  last_mid?: number | null;
};

function Sparkline({ values, width = 96, height = 28 }: { values: number[]; width?: number; height?: number }) {
  if (!values.length) return null;
  const max = Math.max(1, ...values);
  const pad = 2;
  const w = width - pad * 2;
  const h = height - pad * 2;
  const step = values.length > 1 ? w / (values.length - 1) : 0;
  const points = values
    .map((v, i) => `${pad + i * step},${pad + h - (v / max) * h}`)
    .join(' ');
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <polyline
        fill="none"
        stroke="rgba(100, 180, 220, 0.8)"
        strokeWidth="1.5"
        points={points}
      />
    </svg>
  );
}

export default function Home() {
  const [health, setHealth] = useState<{ status?: string } | null>(null);
  const [stats, setStats] = useState<{
    total_events?: number;
    min_ingest_ts?: number;
    max_ingest_ts?: number;
  } | null>(null);
  const [topEvents, setTopEvents] = useState<EventRow[]>([]);
  const [categoryFilter, setCategoryFilter] = useState<string>('all');

  const fetchData = useCallback(() => {
    fetch(`${API}/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ status: 'error' }));
    fetch(`${API}/events/stats`)
      .then((r) => r.json())
      .then(setStats)
      .catch(() => setStats(null));
    fetch(`${API}/events/by_market?limit=${DEFAULT_LIMIT}&sparkline_buckets=12`)
      .then((r) => r.json())
      .then(setTopEvents)
      .catch(() => setTopEvents([]));
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, POLL_MS);
    return () => clearInterval(id);
  }, [fetchData]);

  const categories = useMemo(() => {
    const set = new Set<string>();
    topEvents.forEach((r) => {
      const c = (r.category && r.category.trim()) || null;
      if (c) set.add(c);
    });
    return Array.from(set).sort();
  }, [topEvents]);

  const filtered = useMemo(() => {
    if (categoryFilter === 'all') return topEvents;
    return topEvents.filter((r) => (r.category && r.category.trim()) === categoryFilter);
  }, [topEvents, categoryFilter]);

  const apiDown = health?.status === 'error';

  return (
    <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', alignItems: 'flex-start' }}>
      {/* Main content: uses space and can grow */}
      <div style={{ flex: '1 1 560px', minWidth: 0 }}>
        {apiDown && (
          <div style={{ background: '#2a1a1a', border: '1px solid #a44', padding: 12, marginBottom: 16, borderRadius: 6 }}>
            <strong>API not running.</strong> Run <code style={{ background: '#222', padding: '2px 6px' }}>predex api</code> or <code style={{ background: '#222', padding: '2px 6px' }}>predex api --with-ingestion</code>.
            <br />
            <span style={{ color: '#888', fontSize: 13 }}>Dashboard uses {API}</span>
          </div>
        )}

        <section style={{ marginBottom: 24 }}>
          <h2 style={{ marginTop: 0, marginBottom: 8, fontSize: 18, fontWeight: 600 }}>Top {DEFAULT_LIMIT} by live activity</h2>
          <p style={{ color: '#888', fontSize: 13, marginBottom: 16, lineHeight: 1.45 }}>
            <strong style={{ color: '#aaa' }}>Terminology:</strong> An <strong>event</strong> is one prediction question. A <strong>market</strong> is a tradable outcome (e.g. Yes/No). Below: events ranked by <strong>live order book &amp; price updates</strong> received. Sparkline = last hour (12×5 min).
          </p>

          {categories.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
              <button
                type="button"
                onClick={() => setCategoryFilter('all')}
                style={{
                  padding: '6px 12px',
                  borderRadius: 6,
                  border: '1px solid #333',
                  background: categoryFilter === 'all' ? '#1a3a4a' : '#1a1a1a',
                  color: categoryFilter === 'all' ? '#9ee' : '#aaa',
                  cursor: 'pointer',
                  fontSize: 13,
                }}
              >
                All
              </button>
              {categories.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCategoryFilter(c)}
                  style={{
                    padding: '6px 12px',
                    borderRadius: 6,
                    border: '1px solid #333',
                    background: categoryFilter === c ? '#1a3a4a' : '#1a1a1a',
                    color: categoryFilter === c ? '#9ee' : '#aaa',
                    cursor: 'pointer',
                    fontSize: 13,
                  }}
                >
                  {c}
                </button>
              ))}
            </div>
          )}

          {filtered.length > 0 ? (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {filtered.map((row, i) => {
                const label = (row.title && row.title.trim()) || row.market_id;
                const shortLabel = label.length > 72 ? label.slice(0, 69) + '…' : label;
                const href = `/markets/${encodeURIComponent(row.market_id)}`;
                return (
                  <li
                    key={row.market_id}
                    style={{
                      marginBottom: 8,
                      padding: '12px 14px',
                      background: '#161616',
                      border: '1px solid #2a2a2a',
                      borderRadius: 6,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                      <div style={{ flex: '1 1 240px', minWidth: 0 }}>
                        <span style={{ color: '#666', fontSize: 12, marginRight: 8 }}>#{i + 1}</span>
                        {row.category && (
                          <span
                            style={{
                              marginRight: 8,
                              padding: '2px 6px',
                              background: '#252525',
                              borderRadius: 4,
                              fontSize: 11,
                              color: '#888',
                            }}
                          >
                            {row.category}
                          </span>
                        )}
                        <span style={{ color: '#e0e0e0' }} title={label}>{shortLabel}</span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0 }}>
                        {row.last_mid != null && (
                          <span style={{ fontSize: 15, fontWeight: 600, color: '#7d7', minWidth: 48 }}>
                            {(row.last_mid * 100).toFixed(0)}%
                          </span>
                        )}
                        {row.sparkline && row.sparkline.length > 0 && (
                          <Sparkline values={row.sparkline} width={100} height={28} />
                        )}
                        <span style={{ color: '#888', fontSize: 12, minWidth: 64 }}>{row.event_count.toLocaleString()} updates</span>
                        <a
                          href={href}
                          style={{
                            padding: '6px 12px',
                            background: '#1a3a4a',
                            color: '#7dd',
                            borderRadius: 4,
                            fontSize: 13,
                            textDecoration: 'none',
                          }}
                        >
                          View charts →
                        </a>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p style={{ color: '#666' }}>
              {topEvents.length === 0
                ? 'No data yet. Run ingestion (e.g. predex api --with-ingestion or predex track start).'
                : `No events in category "${categoryFilter}".`}
            </p>
          )}
        </section>
      </div>

      {/* Right column: stats / meta */}
      <div style={{ flex: '0 0 220px', position: 'sticky', top: 24 }}>
        <div style={{ background: '#161616', border: '1px solid #2a2a2a', borderRadius: 8, padding: 16 }}>
          <h3 style={{ marginTop: 0, marginBottom: 12, fontSize: 14, color: '#aaa' }}>Log stats</h3>
          <p style={{ margin: '6px 0', fontSize: 13, color: '#ccc' }}>Status: {health?.status ?? '…'}</p>
          <p style={{ margin: '6px 0', fontSize: 13, color: '#ccc' }}>Total messages: {stats?.total_events?.toLocaleString() ?? '–'}</p>
          {stats?.min_ingest_ts != null && stats?.max_ingest_ts != null && (
            <p style={{ margin: '6px 0', fontSize: 12, color: '#888' }}>
              Range: {new Date(stats.min_ingest_ts).toLocaleTimeString()} – {new Date(stats.max_ingest_ts).toLocaleTimeString()}
            </p>
          )}
          <p style={{ marginTop: 12, fontSize: 11, color: '#666' }}>Refreshes every {POLL_MS / 1000}s</p>
        </div>
      </div>
    </div>
  );
}
