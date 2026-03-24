'use client';

import { useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

export default function WhaleWalletPage({ params }: { params: { address: string } }) {
  const address = (params.address || '').toLowerCase();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    setLoading(true);
    fetch(`${API}/whales/wallets/${encodeURIComponent(address)}?live=true`)
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load wallet'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [address]);

  const tracked = !!data?.tracked;

  const toggleTrack = async () => {
    setBusy(true);
    try {
      if (tracked) {
        await fetch(`${API}/whales/track/${encodeURIComponent(address)}`, { method: 'DELETE' });
      } else {
        await fetch(`${API}/whales/track`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ address }),
        });
      }
      load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h2>Wallet detail</h2>
      <p style={{ color: '#aaa' }}>{address}</p>
      <p><a href="/whales" style={{ color: '#9cf' }}>← Back to whales</a></p>
      {loading && <p>Loading…</p>}
      {error && <p style={{ color: '#f88' }}>{error}</p>}
      {data?.summary && (
        <div style={{ marginBottom: 16 }}>
          <div>30d spend: ${Number(data.summary.spend_30d || 0).toFixed(0)}</div>
          <div>7d spend: ${Number(data.summary.spend_7d || 0).toFixed(0)}</div>
          <div>1d spend: ${Number(data.summary.spend_1d || 0).toFixed(0)}</div>
          <div>Active days: {data.summary.active_days ?? 0}</div>
          <div>Top market concentration: {(Number(data.summary.top_market_concentration_30d || 0) * 100).toFixed(0)}%</div>
        </div>
      )}

      <button
        type="button"
        onClick={toggleTrack}
        disabled={busy}
        style={{ padding: '8px 12px', background: '#333', color: tracked ? '#f88' : '#7d7', border: '1px solid #555' }}
      >
        {busy ? 'Saving…' : tracked ? 'Untrack wallet' : 'Track wallet'}
      </button>

      <h3 style={{ marginTop: 24 }}>Live Data API data</h3>
      <details>
        <summary>Value</summary>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(data?.value ?? null, null, 2)}</pre>
      </details>
      <details>
        <summary>Positions</summary>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(data?.positions ?? null, null, 2)}</pre>
      </details>
      <details>
        <summary>Closed positions</summary>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(data?.closed_positions ?? null, null, 2)}</pre>
      </details>
      <details>
        <summary>Activity</summary>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(data?.activity ?? null, null, 2)}</pre>
      </details>
    </div>
  );
}

