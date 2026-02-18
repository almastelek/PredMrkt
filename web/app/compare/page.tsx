'use client';

import { useCallback, useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';
const COLORS = ['#7dd', '#d77', '#7d7', '#dd7', '#7ad'];

type SeriesEntry = { t: number; [key: string]: number | string | null };

export default function ComparePage() {
  const [markets, setMarkets] = useState<{ market_id: string; title?: string }[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [combined, setCombined] = useState<SeriesEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API}/markets?tracked_only=true&limit=100`)
      .then((r) => r.json())
      .then((d: { markets?: { market_id: string; title?: string }[] }) => setMarkets(d?.markets ?? []))
      .catch(() => setMarkets([]));
  }, []);

  const runCompare = useCallback(() => {
    if (selected.size === 0) return;
    setLoading(true);
    const ids = Array.from(selected);
    Promise.all(
      ids.map((marketId) =>
        fetch(`${API}/markets/${encodeURIComponent(marketId)}/asset`)
          .then((r) => r.json())
          .then((a: { asset_id?: string } | null) => (a?.asset_id ? { marketId, assetId: a.asset_id } : null))
      )
    ).then((assets) => {
      const valid = assets.filter((a): a is { marketId: string; assetId: string } => a != null);
      return Promise.all(
        valid.map(({ marketId, assetId }) =>
          fetch(
            `${API}/markets/${encodeURIComponent(marketId)}/timeseries?asset_id=${encodeURIComponent(assetId)}&max_points=300`
          ).then((r) => r.json()).then((d: { series?: { t: number; mid: number | null }[] }) => ({ marketId, series: d?.series ?? [] }))
        )
      );
    }).then((results) => {
      const allT = new Set<number>();
      const byMarket: { t: number; mid: number }[][] = results.map(({ series }) => {
        const pts = (series as { t: number; mid: number | null }[]).filter((p) => p.mid != null) as { t: number; mid: number }[];
        pts.forEach((p) => allT.add(p.t));
        return pts.sort((a, b) => a.t - b.t);
      });
      const sortedT = Array.from(allT).sort((a, b) => a - b);
      const combinedData: SeriesEntry[] = sortedT.map((t) => {
        const row: SeriesEntry = { t };
        byMarket.forEach((pts, i) => {
          const last = pts.filter((p) => p.t <= t).pop();
          if (last != null) (row as Record<string, number>)[`m${i}`] = last.mid;
        });
        return row;
      });
      setCombined(combinedData);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [selected]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const keys = combined.length ? Object.keys(combined[0]).filter((k) => k !== 't') : [];

  return (
    <div>
      <h2>Compare markets</h2>
      <p style={{ color: '#888', fontSize: 14 }}>Select 2+ markets to overlay mid-price over time (same time axis).</p>
      {markets.length === 0 && (
        <div style={{ background: '#3a2020', border: '1px solid #a44', padding: 12, marginBottom: 16, borderRadius: 4 }}>
          No markets loaded. Start the API in another terminal: <code style={{ background: '#222', padding: '2px 6px' }}>predex api</code>
        </div>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
        {markets.slice(0, 30).map((m) => (
          <label key={m.market_id} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={selected.has(m.market_id ?? '')}
              onChange={() => toggle(m.market_id ?? '')}
            />
            <span>{(m.title || m.market_id || '').slice(0, 40)}…</span>
          </label>
        ))}
      </div>
      <button
        type="button"
        onClick={runCompare}
        disabled={selected.size < 2 || loading}
        style={{ padding: '8px 16px', cursor: selected.size >= 2 && !loading ? 'pointer' : 'not-allowed', background: '#333', color: '#7dd', border: '1px solid #555' }}
      >
        {loading ? 'Loading…' : `Compare ${selected.size} markets`}
      </button>
      {combined.length > 0 && (
        <ResponsiveContainer width="100%" height={400} style={{ marginTop: 24 }}>
          <LineChart data={combined} margin={{ top: 8, right: 8, left: 8, bottom: 24 }}>
            <XAxis dataKey="t" tickFormatter={(t) => new Date(t).toLocaleTimeString()} stroke="#888" />
            <YAxis domain={[0, 1]} stroke="#888" />
            <Tooltip labelFormatter={(t) => new Date(t).toLocaleTimeString()} />
            <Legend />
            {keys.map((k, i) => (
              <Line key={k} type="monotone" dataKey={k} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} name={`Market ${i + 1}`} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
