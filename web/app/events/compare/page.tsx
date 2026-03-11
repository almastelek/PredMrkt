'use client';

import { useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

type ComparePair = {
  id: number;
  label?: string | null;
  polymarket_market_id: string;
  polymarket_title?: string | null;
  kalshi_market_ticker: string;
  kalshi_title?: string | null;
};

type CompareListResponse = {
  pairs: {
    id: number;
    label?: string | null;
    polymarket_market_id: string;
    polymarket_asset_id?: string | null;
    kalshi_event_ticker: string;
    kalshi_market_ticker: string;
    polymarket_title?: string | null;
    kalshi_title?: string | null;
  }[];
};

export default function EventsComparePage() {
  const [pairs, setPairs] = useState<ComparePair[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`${API}/events/compare`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: CompareListResponse) => {
        if (cancelled) return;
        setPairs(
          (data?.pairs ?? []).map((p) => ({
            id: p.id,
            label: p.label,
            polymarket_market_id: p.polymarket_market_id,
            polymarket_title: p.polymarket_title,
            kalshi_market_ticker: p.kalshi_market_ticker,
            kalshi_title: p.kalshi_title,
          })),
        );
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Failed to load pairs');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <h2>Compare events (Polymarket vs Kalshi)</h2>
      <p style={{ color: '#888', fontSize: 14, marginBottom: 16 }}>
        Curated pairs of identical real-world events, with links to a side-by-side comparison view.
      </p>
      <p style={{ marginBottom: 16 }}>
        <a href="/events/compare/candidates" style={{ color: '#9cf', fontSize: 14 }}>
          Suggest new pairs (admin)
        </a>
      </p>
      {loading && <p>Loading pairs…</p>}
      {error && !loading && (
        <div style={{ background: '#3a2020', border: '1px solid #a44', padding: 12, marginBottom: 16, borderRadius: 4 }}>
          <strong style={{ color: '#f88' }}>Error:</strong> {error}
        </div>
      )}
      {!loading && !error && pairs.length === 0 && (
        <p style={{ color: '#888' }}>No event pairs found in the database yet.</p>
      )}
      {pairs.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '8px 4px', borderBottom: '1px solid #333' }}>Label</th>
              <th style={{ textAlign: 'left', padding: '8px 4px', borderBottom: '1px solid #333' }}>Polymarket</th>
              <th style={{ textAlign: 'left', padding: '8px 4px', borderBottom: '1px solid #333' }}>Kalshi</th>
              <th style={{ padding: '8px 4px', borderBottom: '1px solid #333' }} />
            </tr>
          </thead>
          <tbody>
            {pairs.map((p) => (
              <tr key={p.id}>
                <td style={{ padding: '6px 4px', borderBottom: '1px solid #222' }}>
                  {p.label || 'Untitled pair'}
                </td>
                <td style={{ padding: '6px 4px', borderBottom: '1px solid #222' }}>
                  <div style={{ fontSize: 14 }}>
                    {p.polymarket_title || p.polymarket_market_id}
                  </div>
                  <div style={{ fontSize: 12, color: '#777' }}>{p.polymarket_market_id}</div>
                </td>
                <td style={{ padding: '6px 4px', borderBottom: '1px solid #222' }}>
                  <div style={{ fontSize: 14 }}>
                    {p.kalshi_title || p.kalshi_market_ticker}
                  </div>
                  <div style={{ fontSize: 12, color: '#777' }}>{p.kalshi_market_ticker}</div>
                </td>
                <td style={{ padding: '6px 4px', borderBottom: '1px solid #222', textAlign: 'right' }}>
                  <a
                    href={`/events/compare/${p.id}`}
                    style={{
                      padding: '4px 10px',
                      borderRadius: 4,
                      border: '1px solid #555',
                      color: '#7dd',
                      fontSize: 13,
                    }}
                  >
                    View comparison
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

