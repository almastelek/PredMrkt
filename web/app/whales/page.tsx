'use client';

import { useEffect, useState } from 'react';
import { getJSON } from '../../lib/api';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';
const moneyFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
const intFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

type WhaleWallet = {
  wallet: string;
  spend_1d: number;
  spend_7d: number;
  spend_30d: number;
  active_days: number;
  top_market_concentration_30d: number;
  first_seen_ms?: number | null;
  last_seen_ms?: number | null;
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
      getJSON<any>(`/whales/wallets?limit=50`),
      getJSON<any>(`/whales/trades?limit=50`),
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
            <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>First trade</th>
            <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>Latest trade</th>
          </tr>
        </thead>
        <tbody>
          {wallets.map((w) => (
            <tr key={w.wallet}>
              <td style={{ borderBottom: '1px solid #222', padding: 8 }}>
                <a href={`/whales/${w.wallet}`} style={{ color: '#9cf' }}>{w.wallet}</a>
                {w.is_tracked ? <span style={{ color: '#7d7', marginLeft: 8 }}>(tracked)</span> : null}
              </td>
              <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>${moneyFmt.format(w.spend_1d || 0)}</td>
              <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>${moneyFmt.format(w.spend_7d || 0)}</td>
              <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>${moneyFmt.format(w.spend_30d || 0)}</td>
              <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>{intFmt.format(w.active_days || 0)}</td>
              <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>{(w.top_market_concentration_30d * 100).toFixed(0)}%</td>
              <td style={{ borderBottom: '1px solid #222', padding: 8 }}>
                {w.first_seen_ms ? new Date(w.first_seen_ms).toLocaleString() : '-'}
              </td>
              <td style={{ borderBottom: '1px solid #222', padding: 8 }}>
                {w.last_seen_ms ? new Date(w.last_seen_ms).toLocaleString() : '-'}
              </td>
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
              <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>${moneyFmt.format(t.notional_usdc || 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

