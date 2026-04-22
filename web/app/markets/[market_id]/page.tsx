'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import {
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ComposedChart,
  Legend,
  ReferenceLine,
} from 'recharts';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

type RawChartPoint = {
  ts: number;
  mid: number | null;
  spread: number | null;
  depth_bid: number;
  depth_ask: number;
  ofi: number;
};

type ChartPoint = RawChartPoint & {
  time: string;
  best_bid: number | null;
  best_ask: number | null;
  imbalance: number | null;
  imb_up: number | null;
  imb_down: number | null;
  cum_ofi: number;
  depth_total: number;
};

type BookLevel = { price: number; size: number };
type BookSnapshot = {
  ts: number;
  mid: number;
  bids: BookLevel[];
  asks: BookLevel[];
};

const CARD: React.CSSProperties = {
  background: '#1a1a1a',
  border: '1px solid #333',
  borderRadius: 8,
  padding: 16,
  marginBottom: 24,
};

function enrichSeries(series: RawChartPoint[]): ChartPoint[] {
  let cum = 0;
  return series.map((p) => {
    cum += p.ofi || 0;
    const best_bid = p.mid != null && p.spread != null ? p.mid - p.spread / 2 : null;
    const best_ask = p.mid != null && p.spread != null ? p.mid + p.spread / 2 : null;
    const total = (p.depth_bid || 0) + (p.depth_ask || 0);
    const imbalance = total > 0 ? p.depth_bid / total : null;
    const imb_up = imbalance != null ? Math.max(imbalance, 0.5) : null;
    const imb_down = imbalance != null ? Math.min(imbalance, 0.5) : null;
    return {
      ...p,
      time: new Date(p.ts).toLocaleTimeString(),
      best_bid,
      best_ask,
      imbalance,
      imb_up,
      imb_down,
      cum_ofi: cum,
      depth_total: total,
    };
  });
}

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
        setChartSeries(enrichSeries(seriesRes.series || []));
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
  const last = chartSeries.length > 0 ? chartSeries[chartSeries.length - 1] : null;

  if (error) return <p style={{ color: '#c66' }}>{error}</p>;
  if (loading) return <p>Loading…</p>;
  if (!assetId) return null;

  const headingLabel =
    title && title.trim() ? title : marketId.length > 32 ? `${marketId.slice(0, 29)}…` : marketId;

  return (
    <div style={{ maxWidth: 1100 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }} title={title && title.trim() ? title : marketId}>
          Event: {headingLabel}
          {category && (
            <span style={{ marginLeft: 10, fontSize: 14, fontWeight: 400, color: '#888' }}>({category})</span>
          )}
        </h2>
        {last?.mid != null && (
          <div style={{ padding: '6px 12px', background: '#1a2a1a', borderRadius: 6, border: '1px solid #2a4a2a' }}>
            <span style={{ color: '#888', fontSize: 12 }}>Probability</span>
            <div style={{ fontSize: 20, fontWeight: 600, color: '#7d7' }}>{(last.mid * 100).toFixed(1)}%</div>
          </div>
        )}
        {last?.spread != null && (
          <div style={{ padding: '6px 12px', background: '#1a1a2a', borderRadius: 6, border: '1px solid #2a2a4a' }}>
            <span style={{ color: '#888', fontSize: 12 }}>Spread</span>
            <div style={{ fontSize: 20, fontWeight: 600, color: '#dd7' }}>{last.spread.toFixed(3)}</div>
          </div>
        )}
        {last && last.depth_total > 0 && (
          <div style={{ padding: '6px 12px', background: '#1a2a2a', borderRadius: 6, border: '1px solid #2a4a4a' }}>
            <span style={{ color: '#888', fontSize: 12 }}>Book imbalance</span>
            <div style={{ fontSize: 20, fontWeight: 600, color: (last.imbalance ?? 0.5) >= 0.5 ? '#7dd' : '#d77' }}>
              {last.imbalance != null ? `${(last.imbalance * 100).toFixed(0)}% bid` : '—'}
            </div>
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

      {/* Card 1: Depth staircase (cumulative bids/asks around mid) */}
      <section style={CARD}>
        <h3 style={{ marginTop: 0, marginBottom: 4 }}>Depth curve</h3>
        <p style={{ color: '#888', fontSize: 12, marginBottom: 16 }}>
          Cumulative resting size walking outward from mid. Steep = deep/tight book, shallow = thin. Steps mark walls.
        </p>
        {lastSnapshot ? (
          <DepthStaircase snapshot={lastSnapshot} />
        ) : (
          <p style={{ color: '#666' }}>No book snapshot in this window.</p>
        )}
      </section>

      {/* Card 2: Price + spread ribbon + depth background */}
      <section style={CARD}>
        <h3 style={{ marginTop: 0, marginBottom: 4 }}>Price, spread &amp; liquidity</h3>
        <p style={{ color: '#888', fontSize: 12, marginBottom: 16 }}>
          Line = mid (probability). Shaded band = best_bid → best_ask (wider = looser market). Grey fill behind = total
          top‑5 depth.
        </p>
        {chartSeries.length > 0 ? <PriceSpreadChart data={chartSeries} /> : <p style={{ color: '#666' }}>No series.</p>}
      </section>

      {/* Card 3: Book imbalance + cumulative OFI */}
      <section style={CARD}>
        <h3 style={{ marginTop: 0, marginBottom: 4 }}>Book pressure</h3>
        <p style={{ color: '#888', fontSize: 12, marginBottom: 16 }}>
          Green = bid‑heavy (buy support), red = ask‑heavy (sell pressure). Amber line = cumulative order‑flow
          imbalance; persistent slope = directional flow, flat = noise.
        </p>
        {chartSeries.length > 0 ? <PressureChart data={chartSeries} /> : <p style={{ color: '#666' }}>No series.</p>}
      </section>

      {/* Card 4: Depth heatmap over time (Bookmap style) */}
      <section style={CARD}>
        <h3 style={{ marginTop: 0, marginBottom: 4 }}>Depth heatmap</h3>
        <p style={{ color: '#888', fontSize: 12, marginBottom: 16 }}>
          Each column = one bucket; each row = a price tick. Teal = bid liquidity, red = ask liquidity, brighter =
          larger resting size. Yellow line = mid. Watch for walls appearing / getting pulled.
        </p>
        {bookSnapshots.length > 0 ? (
          <DepthHeatmap snapshots={bookSnapshots} />
        ) : (
          <p style={{ color: '#666' }}>No snapshots in this window.</p>
        )}
      </section>

      {chartSeries.length === 0 && bookSnapshots.length === 0 && (
        <p style={{ color: '#666' }}>
          No bucketed data in this window. Ensure ingestion is running and has events for this market.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card 1: Depth staircase
// ---------------------------------------------------------------------------

type StairPoint = { price: number; cum_bid: number | null; cum_ask: number | null };

function DepthStaircase({ snapshot }: { snapshot: BookSnapshot }) {
  const priceWindow = 0.1;
  const { points, totalBid, totalAsk, xMin, xMax } = useMemo(() => {
    const mid = snapshot.mid;
    const bidsDesc = [...snapshot.bids].sort((a, b) => b.price - a.price);
    const asksAsc = [...snapshot.asks].sort((a, b) => a.price - b.price);
    let cb = 0;
    const bidPts: { price: number; cum_bid: number }[] = [];
    for (const lvl of bidsDesc) {
      if (lvl.price < mid - priceWindow) break;
      cb += lvl.size;
      bidPts.push({ price: lvl.price, cum_bid: cb });
    }
    let ca = 0;
    const askPts: { price: number; cum_ask: number }[] = [];
    for (const lvl of asksAsc) {
      if (lvl.price > mid + priceWindow) break;
      ca += lvl.size;
      askPts.push({ price: lvl.price, cum_ask: ca });
    }
    const combined: StairPoint[] = [
      ...bidPts
        .slice()
        .reverse()
        .map((p) => ({ price: p.price, cum_bid: p.cum_bid, cum_ask: null as number | null })),
      ...askPts.map((p) => ({ price: p.price, cum_ask: p.cum_ask, cum_bid: null as number | null })),
    ];
    const xMin = combined.length ? combined[0].price : mid - priceWindow;
    const xMax = combined.length ? combined[combined.length - 1].price : mid + priceWindow;
    return { points: combined, totalBid: cb, totalAsk: ca, xMin, xMax };
  }, [snapshot]);

  return (
    <>
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 12 }}>
        <StatPill label="Best bid" value={snapshot.bids[0]?.price.toFixed(3) ?? '—'} color="#7dd" />
        <StatPill label="Mid" value={snapshot.mid.toFixed(3)} color="#dd7" />
        <StatPill label="Best ask" value={snapshot.asks[0]?.price.toFixed(3) ?? '—'} color="#d77" />
        <StatPill label={`Total bid (±${priceWindow.toFixed(2)})`} value={totalBid.toFixed(0)} color="#7dd" />
        <StatPill label={`Total ask (±${priceWindow.toFixed(2)})`} value={totalAsk.toFixed(0)} color="#d77" />
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={points} margin={{ top: 8, right: 16, left: 8, bottom: 24 }}>
          <XAxis
            dataKey="price"
            type="number"
            domain={[xMin, xMax]}
            tickFormatter={(v) => (typeof v === 'number' ? v.toFixed(2) : v)}
            stroke="#888"
            tick={{ fontSize: 10 }}
          />
          <YAxis stroke="#888" tick={{ fontSize: 10 }} />
          <Tooltip
            content={({ payload }) => {
              const p = payload?.[0]?.payload as StairPoint | undefined;
              if (!p) return null;
              return (
                <div style={{ background: '#222', padding: 8, border: '1px solid #444', fontSize: 12 }}>
                  <div>Price: {p.price.toFixed(3)}</div>
                  {p.cum_bid != null && <div style={{ color: '#7dd' }}>Cum bid: {p.cum_bid.toFixed(0)}</div>}
                  {p.cum_ask != null && <div style={{ color: '#d77' }}>Cum ask: {p.cum_ask.toFixed(0)}</div>}
                </div>
              );
            }}
          />
          <ReferenceLine
            x={snapshot.mid}
            stroke="#dd7"
            strokeDasharray="3 3"
            label={{ value: `mid ${snapshot.mid.toFixed(3)}`, fill: '#dd7', fontSize: 10, position: 'top' }}
          />
          <Area
            type="stepAfter"
            dataKey="cum_bid"
            stroke="#3cb58a"
            fill="#3cb58a"
            fillOpacity={0.3}
            strokeWidth={2}
            connectNulls={false}
            isAnimationActive={false}
            name="Cumulative bid"
          />
          <Area
            type="stepAfter"
            dataKey="cum_ask"
            stroke="#d66060"
            fill="#d66060"
            fillOpacity={0.3}
            strokeWidth={2}
            connectNulls={false}
            isAnimationActive={false}
            name="Cumulative ask"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </>
  );
}

// ---------------------------------------------------------------------------
// Card 2: Price + spread ribbon + depth background
// ---------------------------------------------------------------------------

function PriceSpreadChart({ data }: { data: ChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 24 }}>
        <XAxis dataKey="time" stroke="#888" tick={{ fontSize: 10 }} minTickGap={40} />
        <YAxis yAxisId="price" domain={[0, 1]} stroke="#888" tick={{ fontSize: 10 }} tickFormatter={(v) => (v as number).toFixed(2)} />
        <YAxis yAxisId="depth" orientation="right" stroke="#555" tick={{ fontSize: 10, fill: '#666' }} />
        <Tooltip
          content={({ payload }) => {
            const p = payload?.[0]?.payload as ChartPoint | undefined;
            if (!p) return null;
            return (
              <div style={{ background: '#222', padding: 8, border: '1px solid #444', fontSize: 12 }}>
                <div>{p.time}</div>
                <div style={{ color: '#7dd' }}>Mid: {p.mid?.toFixed(4) ?? '—'}</div>
                <div style={{ color: '#dd7' }}>Spread: {p.spread?.toFixed(4) ?? '—'}</div>
                <div style={{ color: '#888' }}>
                  Depth top‑5: bid {p.depth_bid.toFixed(0)} / ask {p.depth_ask.toFixed(0)}
                </div>
              </div>
            );
          }}
        />
        <Area
          yAxisId="depth"
          type="monotone"
          dataKey="depth_total"
          stroke="none"
          fill="#888"
          fillOpacity={0.08}
          isAnimationActive={false}
          name="Depth (top‑5 total)"
        />
        <Area
          yAxisId="price"
          type="monotone"
          dataKey={(d: ChartPoint) => (d.best_bid != null && d.best_ask != null ? [d.best_bid, d.best_ask] : undefined)}
          stroke="none"
          fill="#7dd"
          fillOpacity={0.2}
          isAnimationActive={false}
          name="Spread (bid → ask)"
        />
        <Line
          yAxisId="price"
          type="monotone"
          dataKey="mid"
          stroke="#7dd"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
          name="Mid"
        />
        <Legend wrapperStyle={{ fontSize: 11, color: '#888' }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Card 3: Book imbalance + cumulative OFI
// ---------------------------------------------------------------------------

function PressureChart({ data }: { data: ChartPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 24 }}>
        <XAxis dataKey="time" stroke="#888" tick={{ fontSize: 10 }} minTickGap={40} />
        <YAxis
          yAxisId="imb"
          domain={[0, 1]}
          stroke="#888"
          tick={{ fontSize: 10 }}
          tickFormatter={(v) => `${Math.round((v as number) * 100)}%`}
        />
        <YAxis yAxisId="cum" orientation="right" stroke="#c84" tick={{ fontSize: 10, fill: '#c84' }} />
        <Tooltip
          content={({ payload }) => {
            const p = payload?.[0]?.payload as ChartPoint | undefined;
            if (!p) return null;
            return (
              <div style={{ background: '#222', padding: 8, border: '1px solid #444', fontSize: 12 }}>
                <div>{p.time}</div>
                <div style={{ color: '#7dd' }}>Mid: {p.mid?.toFixed(4) ?? '—'}</div>
                <div style={{ color: (p.imbalance ?? 0.5) >= 0.5 ? '#3cb58a' : '#d66060' }}>
                  Imbalance: {p.imbalance != null ? `${(p.imbalance * 100).toFixed(1)}% bid` : '—'}
                </div>
                <div style={{ color: '#e8a857' }}>Cum OFI: {p.cum_ofi.toFixed(0)}</div>
              </div>
            );
          }}
        />
        <ReferenceLine yAxisId="imb" y={0.5} stroke="#444" strokeDasharray="2 2" />
        <Area
          yAxisId="imb"
          type="monotone"
          dataKey="imb_up"
          baseValue={0.5}
          stroke="#3cb58a"
          fill="#3cb58a"
          fillOpacity={0.3}
          isAnimationActive={false}
          name="Bid‑heavy"
        />
        <Area
          yAxisId="imb"
          type="monotone"
          dataKey="imb_down"
          baseValue={0.5}
          stroke="#d66060"
          fill="#d66060"
          fillOpacity={0.3}
          isAnimationActive={false}
          name="Ask‑heavy"
        />
        <Line
          yAxisId="imb"
          type="monotone"
          dataKey="mid"
          stroke="#7dd"
          strokeWidth={1.5}
          strokeDasharray="4 2"
          dot={false}
          isAnimationActive={false}
          name="Mid"
        />
        <Line
          yAxisId="cum"
          type="monotone"
          dataKey="cum_ofi"
          stroke="#e8a857"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
          name="Cum OFI"
        />
        <Legend wrapperStyle={{ fontSize: 11, color: '#888' }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Card 4: Depth heatmap over time (Bookmap-style custom SVG)
// ---------------------------------------------------------------------------

const HEATMAP_MAX_COLS = 300;
const TICK_SIZE = 0.01;

function DepthHeatmap({ snapshots }: { snapshots: BookSnapshot[] }) {
  const { cells, midPath, nCols, nBins, minP, maxP, maxSize, yLabels, xLabels } = useMemo(() => {
    const step = Math.max(1, Math.ceil(snapshots.length / HEATMAP_MAX_COLS));
    const downsampled = snapshots.filter((_, i) => i % step === 0);
    let minP = 1,
      maxP = 0,
      maxSize = 0;
    for (const s of downsampled) {
      for (const l of s.bids) {
        if (l.size <= 0) continue;
        if (l.price < minP) minP = l.price;
        if (l.size > maxSize) maxSize = l.size;
      }
      for (const l of s.asks) {
        if (l.size <= 0) continue;
        if (l.price > maxP) maxP = l.price;
        if (l.size > maxSize) maxSize = l.size;
      }
    }
    if (!(maxP > minP)) {
      const mids = downsampled.map((s) => s.mid).filter((m) => m != null);
      const m = mids.length ? mids[Math.floor(mids.length / 2)] : 0.5;
      minP = Math.max(0, m - 0.1);
      maxP = Math.min(1, m + 0.1);
    }
    minP = Math.max(0, Math.floor(minP * 100) / 100);
    maxP = Math.min(1, Math.ceil(maxP * 100) / 100);
    const nBins = Math.max(1, Math.round((maxP - minP) / TICK_SIZE));
    const nCols = downsampled.length;

    const cells: { key: string; x: number; y: number; fill: string }[] = [];
    const priceToBin = (p: number) => Math.floor((p - minP) / TICK_SIZE);
    for (let i = 0; i < nCols; i++) {
      const s = downsampled[i];
      for (const l of s.bids) {
        const b = priceToBin(l.price);
        if (b < 0 || b >= nBins || l.size <= 0) continue;
        const a = Math.min(1, Math.pow(l.size / maxSize, 0.5));
        cells.push({ key: `b-${i}-${b}`, x: i, y: nBins - 1 - b, fill: `rgba(80, 210, 170, ${a.toFixed(3)})` });
      }
      for (const l of s.asks) {
        const b = priceToBin(l.price);
        if (b < 0 || b >= nBins || l.size <= 0) continue;
        const a = Math.min(1, Math.pow(l.size / maxSize, 0.5));
        cells.push({ key: `a-${i}-${b}`, x: i, y: nBins - 1 - b, fill: `rgba(220, 90, 90, ${a.toFixed(3)})` });
      }
    }

    const priceToY = (p: number) => nBins * (1 - (p - minP) / (maxP - minP));
    const midPath = downsampled
      .map((s, i) => `${i + 0.5},${priceToY(s.mid).toFixed(3)}`)
      .join(' ');

    const labelCount = 5;
    const yLabels: { p: number; frac: number }[] = [];
    for (let k = 0; k <= labelCount; k++) {
      const frac = k / labelCount;
      yLabels.push({ p: minP + (maxP - minP) * frac, frac });
    }
    const xCount = Math.min(6, Math.max(2, Math.floor(nCols / 30)));
    const xLabels: { frac: number; label: string }[] = [];
    for (let k = 0; k <= xCount; k++) {
      const idx = Math.round((nCols - 1) * (k / xCount));
      xLabels.push({ frac: k / xCount, label: new Date(downsampled[idx].ts).toLocaleTimeString() });
    }

    return { cells, midPath, nCols, nBins, minP, maxP, maxSize, yLabels, xLabels };
  }, [snapshots]);

  if (nCols === 0) return <p style={{ color: '#666' }}>No snapshots.</p>;

  const heightPx = 320;
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'stretch', height: heightPx }}>
        <div
          style={{
            width: 44,
            position: 'relative',
            color: '#888',
            fontSize: 10,
            textAlign: 'right',
            paddingRight: 6,
          }}
        >
          {yLabels.map((l, i) => (
            <span
              key={i}
              style={{
                position: 'absolute',
                right: 6,
                top: `${(1 - l.frac) * 100}%`,
                transform: 'translateY(-50%)',
              }}
            >
              {l.p.toFixed(2)}
            </span>
          ))}
        </div>
        <div style={{ flex: 1, background: '#0a0a0a', border: '1px solid #222', position: 'relative' }}>
          <svg
            width="100%"
            height="100%"
            viewBox={`0 0 ${nCols} ${nBins}`}
            preserveAspectRatio="none"
            shapeRendering="crispEdges"
            style={{ display: 'block' }}
          >
            {cells.map((c) => (
              <rect key={c.key} x={c.x} y={c.y} width={1} height={1} fill={c.fill} />
            ))}
            <polyline
              points={midPath}
              fill="none"
              stroke="#dd7"
              strokeWidth={1.5}
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        </div>
      </div>
      <div
        style={{
          position: 'relative',
          marginLeft: 44,
          height: 16,
          marginTop: 4,
          color: '#888',
          fontSize: 10,
        }}
      >
        {xLabels.map((l, i) => (
          <span
            key={i}
            style={{
              position: 'absolute',
              left: `${l.frac * 100}%`,
              transform:
                i === 0 ? 'translateX(0)' : i === xLabels.length - 1 ? 'translateX(-100%)' : 'translateX(-50%)',
            }}
          >
            {l.label}
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 12, color: '#888', fontSize: 11 }}>
        <LegendSwatch color="rgb(80, 210, 170)" label="bids" />
        <LegendSwatch color="rgb(220, 90, 90)" label="asks" />
        <span style={{ color: '#dd7' }}>— mid</span>
        <span style={{ marginLeft: 'auto', color: '#666' }}>
          {nCols} buckets · {nBins} price ticks · peak level size {maxSize.toFixed(0)}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small UI helpers
// ---------------------------------------------------------------------------

function StatPill({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ padding: '6px 10px', background: '#222', borderRadius: 4 }}>
      <div style={{ color: '#888', fontSize: 11 }}>{label}</div>
      <div style={{ fontSize: 16, color }}>{value}</div>
    </div>
  );
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span
        style={{
          display: 'inline-block',
          width: 24,
          height: 10,
          background: `linear-gradient(90deg, ${color.replace('rgb', 'rgba').replace(')', ', 0.1)')}, ${color})`,
          borderRadius: 2,
        }}
      />
      {label}
    </span>
  );
}
