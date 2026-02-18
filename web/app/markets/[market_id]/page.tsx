'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

export default function MarketDetailPage() {
  const params = useParams();
  const marketId = params?.market_id as string;
  const [assetId, setAssetId] = useState<string | null>(null);
  const [series, setSeries] = useState<{ t: number; mid: number | null }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSeries = useCallback(() => {
    if (!marketId) return;
    setLoading(true);
    setError(null);
    setSeries([]);
    fetch(`${API}/markets/${encodeURIComponent(marketId)}/asset`)
      .then((r) => {
        if (!r.ok) {
          if (r.status === 404) {
            return r.json().then(() => ({ _noEvents: true }));
          }
          throw new Error(`API ${r.status}`);
        }
        return r.json();
      })
      .then((asset: { asset_id?: string; _noEvents?: boolean } | null) => {
        if (asset && '_noEvents' in asset && asset._noEvents) {
          setError('No ingested events for this market. Run ingestion (predex api --with-ingestion) and wait for data, or try a market from the Home "Event count by market" list.');
          setLoading(false);
          return undefined;
        }
        if (!asset?.asset_id) {
          setError('No events for this market');
          setLoading(false);
          return undefined;
        }
        setAssetId(asset.asset_id);
        return fetch(
          `${API}/markets/${encodeURIComponent(marketId)}/timeseries?asset_id=${encodeURIComponent(asset.asset_id)}&max_points=400`
        ).then((r) => r.json());
      })
      .then((data: { series?: { t: number; mid: number | null }[] } | undefined) => {
        if (data?.series != null) setSeries(data.series);
        setLoading(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      });
  }, [marketId]);

  useEffect(() => {
    fetchSeries();
  }, [fetchSeries]);

  const chartData = series
    .filter((p) => p.mid != null)
    .map((p) => ({ time: new Date(p.t).toLocaleTimeString(), t: p.t, mid: p.mid as number }));

  if (error) return <p style={{ color: '#c66' }}>{error}</p>;
  if (loading) return <p>Loading…</p>;

  return (
    <div>
      <h2>Market: {marketId.slice(0, 24)}…</h2>
      <p style={{ color: '#888', fontSize: 14 }}>Mid-price over time (replayed from event log)</p>
      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 24 }}>
            <XAxis dataKey="time" stroke="#888" />
            <YAxis domain={[0, 1]} stroke="#888" />
            <Tooltip
              content={({ payload }) =>
                payload?.[0] ? (
                  <div style={{ background: '#222', padding: 8, border: '1px solid #444' }}>
                    <div>{(payload[0].payload as { time: string }).time}</div>
                    <div>Mid: {((payload[0].payload as { mid: number }).mid).toFixed(3)}</div>
                  </div>
                ) : null
              }
            />
            <Line type="monotone" dataKey="mid" stroke="#7dd" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <p style={{ color: '#666' }}>No time series data. Ingest events first (predex track start).</p>
      )}
    </div>
  );
}
