'use client';

import { useEffect, useMemo, useState } from 'react';
import { getJSON, sendJSON } from '../../lib/api';

const moneyFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

type SignalAlert = {
  alert_id: string;
  episode_id: string;
  wallet: string;
  condition_id: string | null;
  market_category: string | null;
  scored_at_ms: number;
  base_edge_score: number;
  context_adjusted_score: number;
  insider_likelihood_score: number;
  factor_timing: number | null;
  factor_size: number | null;
  factor_concentration: number | null;
  factor_history: number | null;
  factor_coordination: number | null;
  factor_sports_penalty: number | null;
  reason_codes: string[];
  review_status: string;
  title: string | null;
  outcome: string | null;
  gross_notional_usdc: number | null;
  episode_end_ms: number | null;
};

type SignalsResponse = { alerts: SignalAlert[] };

type RunStats = {
  episodes_upserted: number;
  market_meta_updated: number;
  forward_returns_filled: number;
  wallet_stats_upserted: number;
  alerts_scored: number;
};

const FACTOR_LABELS: Array<{ key: keyof SignalAlert; label: string }> = [
  { key: 'factor_timing', label: 'Timing' },
  { key: 'factor_size', label: 'Size' },
  { key: 'factor_concentration', label: 'Concentr.' },
  { key: 'factor_history', label: 'History' },
  { key: 'factor_coordination', label: 'Coord.' },
];

function FactorRow({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <>
      <span style={{ color: '#888', fontSize: 11 }}>{label}</span>
      {factorBar(value)}
    </>
  );
}

function factorBar(value: number | null | undefined) {
  const v = Math.max(-2, Math.min(3, Number(value ?? 0)));
  const pct = ((v + 2) / 5) * 100;
  const color = v >= 0 ? '#7d7' : '#f88';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 60, height: 6, background: '#222', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color }} />
      </div>
      <span style={{ fontSize: 11, color: '#aaa', minWidth: 28, textAlign: 'right' }}>
        {value == null ? '-' : Number(value).toFixed(2)}
      </span>
    </div>
  );
}

function scoreColor(score: number): string {
  if (score >= 70) return '#f66';
  if (score >= 50) return '#fb6';
  if (score >= 30) return '#dd6';
  return '#888';
}

export default function SignalsPage() {
  const [alerts, setAlerts] = useState<SignalAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minScore, setMinScore] = useState(30);
  const [includeSports, setIncludeSports] = useState(true);
  const [marketCategory, setMarketCategory] = useState<string>('');
  const [running, setRunning] = useState(false);
  const [runStats, setRunStats] = useState<RunStats | null>(null);

  const query = useMemo(() => {
    const qs = new URLSearchParams();
    qs.set('limit', '100');
    qs.set('min_score', String(minScore));
    qs.set('include_sports', String(includeSports));
    if (marketCategory.trim()) qs.set('market_category', marketCategory.trim());
    return `/whales/signals?${qs.toString()}`;
  }, [minScore, includeSports, marketCategory]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getJSON<SignalsResponse>(query)
      .then((r) => {
        if (cancelled) return;
        setAlerts(r?.alerts ?? []);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Failed to load signals');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query]);

  async function handleRun() {
    setRunning(true);
    setError(null);
    try {
      const stats = await sendJSON<RunStats>('/whales/signals/run', 'POST');
      setRunStats(stats);
      // Refresh list after run.
      const r = await getJSON<SignalsResponse>(query);
      setAlerts(r?.alerts ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Run failed');
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <h2>Trader Edge Signals</h2>
      <p style={{ color: '#888', fontSize: 14 }}>
        Scored episodes (bursts of fills by a wallet on a single outcome). "Insider-Likelihood" is a
        statistical edge score after sports/short-horizon adjustments; it is not proof of illicit behavior.
      </p>

      <div
        style={{
          display: 'flex',
          gap: 16,
          alignItems: 'center',
          flexWrap: 'wrap',
          background: '#141414',
          padding: 12,
          borderRadius: 6,
          marginBottom: 16,
        }}
      >
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: '#aaa' }}>
          Min insider score: <strong style={{ color: '#ddd' }}>{minScore}</strong>
          <input
            type="range"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            style={{ width: 180 }}
          />
        </label>
        <label style={{ fontSize: 12, color: '#aaa', display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="checkbox"
            checked={includeSports}
            onChange={(e) => setIncludeSports(e.target.checked)}
          />
          Include sports markets
        </label>
        <label style={{ fontSize: 12, color: '#aaa', display: 'flex', flexDirection: 'column', gap: 4 }}>
          Category contains:
          <input
            type="text"
            value={marketCategory}
            placeholder="politics, crypto..."
            onChange={(e) => setMarketCategory(e.target.value)}
            style={{
              width: 180,
              padding: 4,
              background: '#0b0b0b',
              border: '1px solid #333',
              color: '#ddd',
              borderRadius: 3,
            }}
          />
        </label>
        <div style={{ flex: 1 }} />
        <button
          onClick={handleRun}
          disabled={running}
          style={{
            background: running ? '#333' : '#245',
            color: '#ddd',
            border: '1px solid #456',
            borderRadius: 4,
            padding: '6px 12px',
            cursor: running ? 'default' : 'pointer',
          }}
        >
          {running ? 'Running…' : 'Run pipeline now'}
        </button>
      </div>

      {runStats && (
        <p style={{ color: '#7d7', fontSize: 12, marginTop: -8 }}>
          Last run: episodes={runStats.episodes_upserted}, fwd_returns=
          {runStats.forward_returns_filled}, wallet_stats={runStats.wallet_stats_upserted}, alerts=
          {runStats.alerts_scored}
        </p>
      )}
      {loading && <p>Loading…</p>}
      {error && <p style={{ color: '#f88' }}>{error}</p>}
      {!loading && !error && alerts.length === 0 && (
        <p style={{ color: '#888' }}>
          No alerts for current filters. Try running the pipeline, lowering the min score, or running
          <code> predex whales ingest</code> first to collect more trades.
        </p>
      )}

      {alerts.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>Insider</th>
              <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>When</th>
              <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>Wallet</th>
              <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>Market</th>
              <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>Category</th>
              <th style={{ textAlign: 'right', borderBottom: '1px solid #333', padding: 8 }}>Notional</th>
              <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>Factors</th>
              <th style={{ textAlign: 'left', borderBottom: '1px solid #333', padding: 8 }}>Reasons</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a) => {
              const insider = Number(a.insider_likelihood_score ?? 0);
              const base = Number(a.base_edge_score ?? 0);
              const adj = Number(a.context_adjusted_score ?? 0);
              const sports = (a.market_category || '').toLowerCase().includes('sport');
              return (
                <tr key={a.alert_id}>
                  <td style={{ borderBottom: '1px solid #222', padding: 8 }}>
                    <div
                      title={`base=${base.toFixed(1)}  adj=${adj.toFixed(1)}  insider=${insider.toFixed(1)}`}
                      style={{
                        fontWeight: 700,
                        color: scoreColor(insider),
                        fontSize: 16,
                      }}
                    >
                      {insider.toFixed(0)}
                    </div>
                    <div style={{ color: '#666', fontSize: 10 }}>
                      base {base.toFixed(0)} · adj {adj.toFixed(0)}
                    </div>
                  </td>
                  <td style={{ borderBottom: '1px solid #222', padding: 8, whiteSpace: 'nowrap', color: '#aaa' }}>
                    {a.episode_end_ms ? new Date(a.episode_end_ms).toLocaleString() : '-'}
                  </td>
                  <td style={{ borderBottom: '1px solid #222', padding: 8 }}>
                    <a href={`/whales/${a.wallet}`} style={{ color: '#9cf' }}>
                      {a.wallet.slice(0, 10)}…
                    </a>
                  </td>
                  <td style={{ borderBottom: '1px solid #222', padding: 8 }}>
                    {a.title ? (
                      <div>
                        <div>{a.title}</div>
                        {a.outcome && (
                          <div style={{ color: '#888', fontSize: 11 }}>Outcome: {a.outcome}</div>
                        )}
                      </div>
                    ) : (
                      <span style={{ color: '#666' }}>{a.condition_id || '-'}</span>
                    )}
                  </td>
                  <td style={{ borderBottom: '1px solid #222', padding: 8, color: sports ? '#fb6' : '#aaa' }}>
                    {a.market_category || '—'}
                  </td>
                  <td style={{ textAlign: 'right', borderBottom: '1px solid #222', padding: 8 }}>
                    {a.gross_notional_usdc != null
                      ? `$${moneyFmt.format(a.gross_notional_usdc)}`
                      : '—'}
                  </td>
                  <td style={{ borderBottom: '1px solid #222', padding: 8 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 4 }}>
                      {FACTOR_LABELS.map((f) => (
                        <FactorRow
                          key={f.key as string}
                          label={f.label}
                          value={a[f.key] as number | null | undefined}
                        />
                      ))}
                    </div>
                  </td>
                  <td style={{ borderBottom: '1px solid #222', padding: 8 }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {(a.reason_codes ?? []).map((code) => (
                        <span
                          key={code}
                          style={{
                            background: code === 'SPORTS_MARKET' ? '#3a2' : '#245',
                            color: '#ddd',
                            border: '1px solid #456',
                            fontSize: 10,
                            padding: '2px 6px',
                            borderRadius: 3,
                          }}
                        >
                          {code}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
