'use client';

import { useCallback, useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';
const POLL_MS = 10000;

type Market = { market_id?: string; venue?: string; title?: string; category?: string; volume_24h?: number; liquidity?: number; active?: boolean };

export default function MarketsPage() {
  const [data, setData] = useState<{ markets: Market[]; total: number } | null>(null);
  const [fetchFailed, setFetchFailed] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const fetchData = useCallback(() => {
    fetch(`${API}/markets?tracked_only=true&limit=100`)
      .then((r) => r.json())
      .then((d) => {
        setData(d);
        setFetchFailed(false);
      })
      .catch(() => setFetchFailed(true));
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, POLL_MS);
    return () => clearInterval(id);
  }, [fetchData]);

  const markets = data?.markets ?? [];
  const total = data?.total ?? 0;
  const display = showAll ? markets : markets.slice(0, 50);

  const apiDown = fetchFailed;

  return (
    <div>
      {apiDown && (
        <div style={{ background: '#3a2020', border: '1px solid #a44', padding: 12, marginBottom: 16, borderRadius: 4 }}>
          <strong>API not running.</strong> Start it in another terminal: <code style={{ background: '#222', padding: '2px 6px' }}>predex api</code>
        </div>
      )}
      <h2>Tracked Markets ({total} total)</h2>
      <p style={{ color: '#888', fontSize: 14 }}>Refreshes every {POLL_MS / 1000}s. Data is from DB (run predex track start to ingest).</p>
      {total > 50 && (
        <button
          type="button"
          onClick={() => setShowAll(!showAll)}
          style={{ marginBottom: 16, padding: '6px 12px', cursor: 'pointer', background: '#333', color: '#7dd', border: '1px solid #555' }}
        >
          {showAll ? 'Show 50' : 'Show all'}
        </button>
      )}
      <ul style={{ listStyle: 'none', padding: 0 }}>
        {display.map((m, i) => (
          <li key={m.market_id ?? i} style={{ padding: '10px 0', borderBottom: '1px solid #333', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <span style={{ flex: '1 1 300px' }}>{(m.title || m.market_id || '').slice(0, 70)}</span>
            <span style={{ color: '#888' }}>vol: {(m.volume_24h ?? 0).toLocaleString()} liq: {(m.liquidity ?? 0).toLocaleString()}</span>
            {m.category && <span style={{ color: '#6a6' }}>{m.category}</span>}
            <a href={`/markets/${encodeURIComponent(m.market_id ?? '')}`} style={{ color: '#7dd', marginLeft: 8 }}>Chart</a>
          </li>
        ))}
      </ul>
      {markets.length === 0 && <p style={{ color: '#666' }}>No tracked markets. Run: predex markets discover</p>}
    </div>
  );
}
