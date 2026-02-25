'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import {
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Legend,
  ReferenceLine,
} from 'recharts';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

type ChartPoint = {
  ts: number;
  mid: number | null;
  spread: number | null;
  depth_bid: number;
  depth_ask: number;
  ofi: number;
  time: string;
};

type BookSnapshot = {
  ts: number;
  mid: number;
  bids: { price: number; size: number }[];
  asks: { price: number; size: number }[];
};

export default function MarketDetailPage() {
  const params = useParams();
  const marketId = params?.market_id as string;
  const [assetId, setAssetId] = useState<string | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [category, setCategory] = useState<string | null>(null);
  const [chartSeries, setChartSeries] = useState<ChartPoint[]>([]);
  const [bookSnapshots, setBookSnapshots] = useState<BookSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [windowMin, setWindowMin] = useState(30);
  const isInitialLoad = assetId === null && !error;

  const fetchData = useCallback(() => {
    if (!marketId) return;
    if (isInitialLoad) {
      setLoading(true);
      setError(null);
      setChartSeries([]);
      setBookSnapshots([]);
    }
    fetch(`${API}/markets/${encodeURIComponent(marketId)}/asset`)
      .then((r) => {
        if (!r.ok) {
          if (r.status === 404) return r.json().then(() => ({ _noEvents: true }));
          throw new Error(`API ${r.status}`);
        }
        return r.json();
      })
      .then((asset: { asset_id?: string; title?: string; category?: string; _noEvents?: boolean } | null) => {
        if (asset && '_noEvents' in asset && asset._noEvents) {
          setError(
            'No ingested events for this market. Run ingestion (predex api --with-ingestion) and wait for data, or try a market from the Home list.'
          );
          setLoading(false);
          return undefined;
        }
        if (!asset?.asset_id) {
          setError('No events for this market');
          setLoading(false);
          return undefined;
        }
        setAssetId(asset.asset_id);
        setTitle(asset.title ?? null);
        setCategory(asset.category ?? null);
        const end = Date.now();
        const start = end - windowMin * 60 * 1000;
        const q = `asset_id=${encodeURIComponent(asset.asset_id)}&start_ts=${start}&end_ts=${end}`;
        return Promise.all([
          fetch(`${API}/markets/${encodeURIComponent(marketId)}/chart/series?${q}&resolution=1000&depth_n=5`).then(
            (r) => r.json()
          ),
          fetch(
            `${API}/markets/${encodeURIComponent(marketId)}/chart/book_heatmap?${q}&resolution=1000&tick_size=0.01&ticks_around_mid=50`
          ).then((r) => r.json()),
        ]);
      })
      .then((result) => {
        if (!result) return;
        const [seriesRes, heatmapRes] = result;
        const series: ChartPoint[] = (seriesRes.series || []).map((p: { ts: number; mid: number | null; spread: number | null; depth_bid: number; depth_ask: number; ofi: number }) => ({
          ...p,
          time: new Date(p.ts).toLocaleTimeString(),
        }));
        setChartSeries(series);
        setBookSnapshots(heatmapRes.snapshots || []);
        setLoading(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      });
  }, [marketId, windowMin, isInitialLoad]);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 10000);
    return () => clearInterval(id);
  }, [fetchData]);

  const lastSnapshot = bookSnapshots.length > 0 ? bookSnapshots[bookSnapshots.length - 1] : null;

  if (error) return <p style={{ color: '#c66' }}>{error}</p>;
  if (loading) return <p>Loading…</p>;
  if (!assetId) return null;

  const headingLabel = title && title.trim() ? title : (marketId.length > 32 ? `${marketId.slice(0, 29)}…` : marketId);
  const lastMid = chartSeries.length > 0 ? chartSeries[chartSeries.length - 1]?.mid : null;

  return (
    <div style={{ maxWidth: 1000 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }} title={title && title.trim() ? title : marketId}>
          Event: {headingLabel}
          {category && (
            <span style={{ marginLeft: 10, fontSize: 14, fontWeight: 400, color: '#888' }}>({category})</span>
          )}
        </h2>
        {lastMid != null && (
          <div style={{ padding: '6px 12px', background: '#1a2a1a', borderRadius: 6, border: '1px solid #2a4a2a' }}>
            <span style={{ color: '#888', fontSize: 12 }}>Probability</span>
            <div style={{ fontSize: 20, fontWeight: 600, color: '#7d7' }}>{(lastMid * 100).toFixed(1)}%</div>
          </div>
        )}
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#888', fontSize: 14 }}>
          Window:
          <select
            value={windowMin}
            onChange={(e) => setWindowMin(Number(e.target.value))}
            style={{ background: '#222', color: '#e0e0e0', border: '1px solid #444', padding: '4px 8px' }}
          >
            <option value={5}>5m</option>
            <option value={15}>15m</option>
            <option value={30}>30m</option>
            <option value={60}>1h</option>
          </select>
        </label>
      </div>

      {/* Card 1: Orderbook depth heatmap (simplified: latest snapshot + depth over time) */}
      <section style={{ background: '#1a1a1a', border: '1px solid #333', borderRadius: 8, padding: 16, marginBottom: 24 }}>
        <h3 style={{ marginTop: 0, marginBottom: 8 }}>Orderbook depth</h3>
        <p style={{ color: '#888', fontSize: 12, marginBottom: 16 }}>
          Top: asks (supply). Bottom: bids (demand). Right: depth over time.
        </p>
        {lastSnapshot && (
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 16 }}>
            <div style={{ flex: '1 1 280px' }}>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>Asks (last bucket)</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {lastSnapshot.asks.slice(0, 12).map((lev, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 48, color: '#d77' }}>{lev.price.toFixed(2)}</span>
                    <div
                      style={{
                        height: 14,
                        background: 'linear-gradient(90deg, #4a2020 0%, #8a3030 100%)',
                        width: `${Math.min(100, (lev.size / 500) * 100)}%`,
                        borderRadius: 2,
                      }}
                    />
                    <span style={{ color: '#888', fontSize: 11 }}>{lev.size.toFixed(0)}</span>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ flex: '1 1 280px' }}>
              <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>Bids (last bucket)</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {lastSnapshot.bids.slice(0, 12).map((lev, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 48, color: '#7dd' }}>{lev.price.toFixed(2)}</span>
                    <div
                      style={{
                        height: 14,
                        background: 'linear-gradient(90deg, #204a4a 0%, #308a8a 100%)',
                        width: `${Math.min(100, (lev.size / 500) * 100)}%`,
                        borderRadius: 2,
                      }}
                    />
                    <span style={{ color: '#888', fontSize: 11 }}>{lev.size.toFixed(0)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
        {chartSeries.length > 0 && (
          <ResponsiveContainer width="100%" height={180}>
            <ComposedChart data={chartSeries} margin={{ top: 8, right: 8, left: 8, bottom: 24 }}>
              <XAxis dataKey="time" stroke="#888" tick={{ fontSize: 10 }} />
              <YAxis stroke="#888" tick={{ fontSize: 10 }} />
              <Tooltip
                content={({ payload }) =>
                  payload?.[0] ? (
                    <div style={{ background: '#222', padding: 8, border: '1px solid #444' }}>
                      <div>{(payload[0].payload as ChartPoint).time}</div>
                      <div>Bid depth: {(payload[0].payload as ChartPoint).depth_bid?.toFixed(0)}</div>
                      <div>Ask depth: {(payload[0].payload as ChartPoint).depth_ask?.toFixed(0)}</div>
                    </div>
                  ) : null
                }
              />
              <Line type="monotone" dataKey="depth_ask" stroke="#8a3030" strokeWidth={1} dot={false} name="Ask depth" />
              <Line type="monotone" dataKey="depth_bid" stroke="#308a8a" strokeWidth={1} dot={false} name="Bid depth" />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </section>

      {/* Card 2: Spread + liquidity tightness */}
      <section style={{ background: '#1a1a1a', border: '1px solid #333', borderRadius: 8, padding: 16, marginBottom: 24 }}>
        <h3 style={{ marginTop: 0, marginBottom: 8 }}>Spread &amp; top-of-book depth</h3>
        <p style={{ color: '#888', fontSize: 12, marginBottom: 16 }}>
          Spread (best_ask − best_bid) and sum of top 5 levels each side.
        </p>
        {chartSeries.length > 0 && (
          <>
            <div style={{ display: 'flex', gap: 24, marginBottom: 16, flexWrap: 'wrap' }}>
              <div style={{ padding: '8px 12px', background: '#222', borderRadius: 4 }}>
                <span style={{ color: '#888', fontSize: 11 }}>Current spread</span>
                <div style={{ fontSize: 18, color: '#dd7' }}>
                  {chartSeries[chartSeries.length - 1]?.spread != null
                    ? chartSeries[chartSeries.length - 1].spread!.toFixed(4)
                    : '—'}
                </div>
              </div>
              <div style={{ padding: '8px 12px', background: '#222', borderRadius: 4 }}>
                <span style={{ color: '#888', fontSize: 11 }}>Bid depth (top 5)</span>
                <div style={{ fontSize: 18, color: '#7dd' }}>
                  {chartSeries[chartSeries.length - 1]?.depth_bid?.toFixed(0) ?? '—'}
                </div>
              </div>
              <div style={{ padding: '8px 12px', background: '#222', borderRadius: 4 }}>
                <span style={{ color: '#888', fontSize: 11 }}>Ask depth (top 5)</span>
                <div style={{ fontSize: 18, color: '#d77' }}>
                  {chartSeries[chartSeries.length - 1]?.depth_ask?.toFixed(0) ?? '—'}
                </div>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={chartSeries} margin={{ top: 8, right: 8, left: 8, bottom: 24 }}>
                <XAxis dataKey="time" stroke="#888" tick={{ fontSize: 10 }} />
                <YAxis yAxisId="left" stroke="#888" tick={{ fontSize: 10 }} />
                <YAxis yAxisId="right" orientation="right" stroke="#888" tick={{ fontSize: 10 }} />
                <Tooltip
                  content={({ payload }) =>
                    payload?.[0] ? (
                      <div style={{ background: '#222', padding: 8, border: '1px solid #444' }}>
                        <div>{(payload[0].payload as ChartPoint).time}</div>
                        <div>Spread: {(payload[0].payload as ChartPoint).spread?.toFixed(4) ?? '—'}</div>
                        <div>Bid depth: {(payload[0].payload as ChartPoint).depth_bid?.toFixed(0)}</div>
                        <div>Ask depth: {(payload[0].payload as ChartPoint).depth_ask?.toFixed(0)}</div>
                      </div>
                    ) : null
                  }
                />
                <Line yAxisId="left" type="monotone" dataKey="spread" stroke="#dd7" strokeWidth={2} dot={false} name="Spread" />
                <Line yAxisId="right" type="monotone" dataKey="depth_bid" stroke="#7dd" strokeWidth={1} dot={false} name="Bid depth" />
                <Line yAxisId="right" type="monotone" dataKey="depth_ask" stroke="#d77" strokeWidth={1} dot={false} name="Ask depth" />
                <Legend />
              </ComposedChart>
            </ResponsiveContainer>
          </>
        )}
      </section>

      {/* Card 3: OFI + mid price */}
      <section style={{ background: '#1a1a1a', border: '1px solid #333', borderRadius: 8, padding: 16, marginBottom: 24 }}>
        <h3 style={{ marginTop: 0, marginBottom: 8 }}>Order flow imbalance (OFI) &amp; mid price</h3>
        <p style={{ color: '#888', fontSize: 12, marginBottom: 16 }}>
          Positive OFI = buy pressure, negative = sell pressure. Mid = (best_bid + best_ask) / 2.
        </p>
        {chartSeries.length > 0 && (
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={chartSeries} margin={{ top: 8, right: 8, left: 8, bottom: 24 }}>
              <XAxis dataKey="time" stroke="#888" tick={{ fontSize: 10 }} />
              <YAxis yAxisId="mid" domain={[0, 1]} stroke="#888" tick={{ fontSize: 10 }} />
              <YAxis yAxisId="ofi" orientation="right" stroke="#888" tick={{ fontSize: 10 }} />
              <Tooltip
                content={({ payload }) =>
                  payload?.[0] ? (
                    <div style={{ background: '#222', padding: 8, border: '1px solid #444' }}>
                      <div>{(payload[0].payload as ChartPoint).time}</div>
                      <div>Mid: {(payload[0].payload as ChartPoint).mid?.toFixed(4) ?? '—'}</div>
                      <div>OFI: {(payload[0].payload as ChartPoint).ofi?.toFixed(2) ?? '—'}</div>
                    </div>
                  ) : null
                }
              />
              <ReferenceLine yAxisId="mid" y={0.5} stroke="#444" strokeDasharray="2 2" />
              <Line yAxisId="mid" type="monotone" dataKey="mid" stroke="#7dd" strokeWidth={2} dot={false} name="Mid" />
              <Bar yAxisId="ofi" dataKey="ofi" fill="#4488aa" fillOpacity={0.6} radius={[2, 2, 0, 0]} name="OFI" />
              <Legend />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </section>

      {chartSeries.length === 0 && bookSnapshots.length === 0 && (
        <p style={{ color: '#666' }}>No bucketed data in this window. Ensure ingestion is running and has events for this market.</p>
      )}
    </div>
  );
}
