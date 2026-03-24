'use client';

import { useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

type WhaleWallet = {
  wallet: string;
  spend_1d: number;
  spend_7d: number;
  spend_30d: number;
  active_days: number;
  top_market_concentration_30d: number;
  is_tracked?: boolean;
};

type WhaleTrade = {
  wallet: string;
  side?: string;
  title?: string;
  outcome?: string;
  notional_usdc: number;
  timestamp_ms: number;
};

export default function WhalesPage() {
  const [wallets, setWallets] = useState<WhaleWallet[]>([]);
  const [trades, setTrades] = useState<WhaleTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      fetch(`${API}/whales/wallets?limit=50`).then((r) => r.json()),
      fetch(`${API}/whales/trades?limit=50`).then((r) => r.json()),
    ])
      .then(([w, t]) => {
        if (cancelled) return;
        setWallets(w?.wallets ?? []);
        setTrades(t?.trades ?? []);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Failed to load whales');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <h2>Whales / large-flow wallets</h2>
      <p style={{ color: '#888', fontSize: 14 }}>
        Heuristic signals based on Polymarket Data API trades. This is not proof of insider behavior.
      </p>
      {loading && <p>Loading…</p>}
      {error && <p style={{ color: '#f88' }}>{error}</p>}

      <h3 style={{ marginTop: 24 }}>Top wallets (30d spend)</h3>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>Wallet</th>
            <th style={{ textAlign: 'right', borderBottom: '1px solid #333', padding: 8 }}>1d</th>
            <th style={{ textAlign: 'right', borderBottom: '1px solid #333', padding: 8 }}>7d</th>
            <th style={{ textAlign: 'right', borderBottom: '1px solid #333', padding: 8 }}>30d</th>
            <th style={{ textAlign: 'right', borderBottom: '1px solid #333', padding: 8 }}>Active days</th>
            <th style={{ textAlign: 'right', borderBottom: '1px solid #333', padding: 8 }}>Top market %</th>
          </tr>
        </thead>
        <tbody>
          {wallets.map((w) => (
            <tr key={w.wallet}>
              <td style={{ borderBottom: '1px solid #222', padding: 8 }}>
                <a href={`/whales/${w.wallet}`} style={{ color: '#9cf' }}>{w.wallet}</a>
                {w.is_tracked ? <span style={{ color: '#7d7', marginLeft: 8 }}>(tracked)</span> : null}
              </td>
              <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>${w.spend_1d.toFixed(0)}</td>
              <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>${w.spend_7d.toFixed(0)}</td>
              <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>${w.spend_30d.toFixed(0)}</td>
              <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>{w.active_days}</td>
              <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>{(w.top_market_concentration_30d * 100).toFixed(0)}%</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: 24 }}>Recent large trades</h3>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>Time</th>
            <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>Wallet</th>
            <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>Market</th>
            <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>Side</th>
            <th style={{ textAlign: 'right', borderBottom: '1px solid #333', padding: 8 }}>Notional</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, idx) => (
            <tr key={`${t.wallet}-${t.timestamp_ms}-${idx}`}>
              <td style={{ borderBottom: '1px solid #222', padding: 8 }}>{new Date(t.timestamp_ms).toLocaleString()}</td>
              <td style={{ borderBottom: '1px solid #222', padding: 8 }}>
                <a href={`/whales/${t.wallet}`} style={{ color: '#9cf' }}>{t.wallet}</a>
              </td>
              <td style={{ borderBottom: '1px solid #222', padding: 8 }}>{t.title || '-'}</td>
              <td style={{ borderBottom: '1px solid #222', padding: 8 }}>{t.side || '-'} {t.outcome ? `(${t.outcome})` : ''}</td>
              <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>${t.notional_usdc.toFixed(0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

