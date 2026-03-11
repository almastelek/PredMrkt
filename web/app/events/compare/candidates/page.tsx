'use client';

import { useCallback, useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

type Candidate = {
  score: number;
  polymarket_market_id: string;
  polymarket_title?: string | null;
  kalshi_event_ticker: string;
  kalshi_market_ticker: string;
  kalshi_title?: string | null;
  kalshi_strike_ts?: number | null;
};

type CompareCandidatesResponse = {
  candidates: Candidate[];
};

export default function CompareCandidatesPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [minScore, setMinScore] = useState(0.4);
  const [acting, setActing] = useState<string | null>(null);

  const fetchCandidates = useCallback(() => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ limit: '50', min_score: String(minScore) });
    fetch(`${API}/events/compare/candidates?${params}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: CompareCandidatesResponse) => {
        setCandidates(data?.candidates ?? []);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Failed to load candidates');
        setCandidates([]);
      })
      .finally(() => setLoading(false));
  }, [minScore]);

  useEffect(() => {
    fetchCandidates();
  }, [fetchCandidates]);

  const approve = (c: Candidate) => {
    const key = `${c.polymarket_market_id}:${c.kalshi_market_ticker}`;
    setActing(key);
    fetch(`${API}/events/compare/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        polymarket_market_id: c.polymarket_market_id,
        kalshi_event_ticker: c.kalshi_event_ticker,
        kalshi_market_ticker: c.kalshi_market_ticker,
      }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        setCandidates((prev) => prev.filter((x) => x.polymarket_market_id !== c.polymarket_market_id || x.kalshi_market_ticker !== c.kalshi_market_ticker));
      })
      .catch(() => setError('Approve failed'))
      .finally(() => setActing(null));
  };

  const reject = (c: Candidate) => {
    const key = `${c.polymarket_market_id}:${c.kalshi_market_ticker}`;
    setActing(key);
    fetch(`${API}/events/compare/candidates/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        polymarket_market_id: c.polymarket_market_id,
        kalshi_market_ticker: c.kalshi_market_ticker,
      }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        setCandidates((prev) => prev.filter((x) => x.polymarket_market_id !== c.polymarket_market_id || x.kalshi_market_ticker !== c.kalshi_market_ticker));
      })
      .catch(() => setError('Reject failed'))
      .finally(() => setActing(null));
  };

  return (
    <div>
      <h2>Suggest event pairs (admin)</h2>
      <p style={{ color: '#888', fontSize: 14, marginBottom: 16 }}>
        Heuristic matches by title similarity. Approve to add to curated pairs; reject to hide from future suggestions.
      </p>
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 14 }}>Min score:</span>
          <input
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            style={{ width: 64, padding: 4, background: '#222', color: '#eee', border: '1px solid #555' }}
          />
        </label>
        <button
          type="button"
          onClick={() => fetchCandidates()}
          disabled={loading}
          style={{ padding: '6px 12px', background: '#333', color: '#7dd', border: '1px solid #555', cursor: loading ? 'not-allowed' : 'pointer' }}
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
        <a href="/events/compare" style={{ color: '#7dd', fontSize: 14 }}>← Back to pairs</a>
      </div>
      {error && (
        <div style={{ background: '#3a2020', border: '1px solid #a44', padding: 12, marginBottom: 16, borderRadius: 4 }}>
          {error}
        </div>
      )}
      {loading && candidates.length === 0 && <p>Loading candidates…</p>}
      {!loading && candidates.length === 0 && !error && (
        <p style={{ color: '#888' }}>No candidate pairs at this score threshold. Try lowering min score or adding more Polymarket markets to the DB.</p>
      )}
      {candidates.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '8px 6px', borderBottom: '1px solid #333' }}>Score</th>
              <th style={{ textAlign: 'left', padding: '8px 6px', borderBottom: '1px solid #333' }}>Polymarket</th>
              <th style={{ textAlign: 'left', padding: '8px 6px', borderBottom: '1px solid #333' }}>Kalshi</th>
              <th style={{ padding: '8px 6px', borderBottom: '1px solid #333' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => {
              const key = `${c.polymarket_market_id}:${c.kalshi_market_ticker}`;
              const busy = acting === key;
              return (
                <tr key={key}>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #222' }}>
                    <strong>{(c.score * 100).toFixed(0)}%</strong>
                  </td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #222' }}>
                    <div style={{ fontSize: 14 }}>{c.polymarket_title || c.polymarket_market_id}</div>
                    <div style={{ fontSize: 11, color: '#666' }}>{c.polymarket_market_id}</div>
                  </td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #222' }}>
                    <div style={{ fontSize: 14 }}>{c.kalshi_title || c.kalshi_market_ticker}</div>
                    <div style={{ fontSize: 11, color: '#666' }}>{c.kalshi_event_ticker} / {c.kalshi_market_ticker}</div>
                  </td>
                  <td style={{ padding: '8px 6px', borderBottom: '1px solid #222' }}>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => approve(c)}
                      style={{
                        marginRight: 8,
                        padding: '4px 10px',
                        background: '#1a3a1a',
                        color: '#7d7',
                        border: '1px solid #3a5a3a',
                        cursor: busy ? 'not-allowed' : 'pointer',
                        borderRadius: 4,
                      }}
                    >
                      {busy ? '…' : 'Approve'}
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => reject(c)}
                      style={{
                        padding: '4px 10px',
                        background: '#3a201a',
                        color: '#d77',
                        border: '1px solid #5a3a3a',
                        cursor: busy ? 'not-allowed' : 'pointer',
                        borderRadius: 4,
                      }}
                    >
                      Reject
                    </button>
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
