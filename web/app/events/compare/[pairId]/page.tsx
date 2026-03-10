'use client';

import { useEffect, useMemo, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

type CompareDetail = {
  id: number;
  label?: string | null;
  polymarket_market_id: string;
  polymarket_asset_id?: string | null;
  kalshi_event_ticker: string;
  kalshi_market_ticker: string;
  polymarket?: {
    market_id?: string;
    title?: string | null;
    category?: string | null;
    outcomes?: unknown;
  };
  kalshi?: {
    ticker?: string;
    title?: string | null;
    subtitle?: string | null;
    series_ticker?: string | null;
    event_ticker?: string | null;
    [key: string]: unknown;
  };
};

type TimeseriesResponse = {
  market_id: string;
  asset_id: string;
  series: { t: number; mid: number | null }[];
};

type SeriesRow = { t: number; polymarket?: number; kalshi?: number };

async function fetchJSON<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) {
    throw new Error(`HTTP ${r.status} for ${url}`);
  }
  return (await r.json()) as T;
}

async function loadPolymarketSeries(
  marketId: string,
  assetIdHint?: string | null,
): Promise<TimeseriesResponse | null> {
  try {
    let assetId = assetIdHint ?? null;
    if (!assetId) {
      const meta = await fetchJSON<{ asset_id?: string | null }>(
        `${API}/markets/${encodeURIComponent(marketId)}/asset`,
      );
      if (!meta.asset_id) return null;
      assetId = meta.asset_id;
    }
    const url = `${API}/markets/${encodeURIComponent(
      marketId,
    )}/timeseries?asset_id=${encodeURIComponent(assetId)}&max_points=300`;
    const data = await fetchJSON<TimeseriesResponse>(url);
    return data;
  } catch {
    return null;
  }
}

type KalshiCandle = {
  start_ts?: number;
  end_ts?: number;
  close?: number;
  close_yes?: number;
  last_price?: number;
  [key: string]: unknown;
};

async function loadKalshiSeries(
  marketTicker: string,
  windowMs?: { start: number; end: number },
): Promise<{ t: number; price: number }[] | null> {
  try {
    const base = 'https://api.elections.kalshi.com/trade-api/v2';
    const m = await fetchJSON<{ market?: { series_ticker?: string | null; event_ticker?: string | null } } & {
      series_ticker?: string | null;
      event_ticker?: string | null;
    }>(`${base}/markets/${encodeURIComponent(marketTicker)}`);
    const market = (m as any).market ?? m;
    const seriesTicker =
      (market.series_ticker as string | null) || (market.event_ticker as string | null);
    if (!seriesTicker) return null;

    const endMs = windowMs?.end ?? Date.now();
    const startMs = windowMs?.start ?? endMs - 6 * 60 * 60 * 1000;
    const startSec = Math.floor(startMs / 1000);
    const endSec = Math.floor(endMs / 1000);

    const params = new URLSearchParams({
      start_ts: String(startSec),
      end_ts: String(endSec),
      period_interval: '60',
    });
    const candlesResp = await fetchJSON<{ candlesticks?: KalshiCandle[]; candles?: KalshiCandle[] }>(
      `${base}/series/${encodeURIComponent(seriesTicker)}/markets/${encodeURIComponent(
        marketTicker,
      )}/candlesticks?${params.toString()}`,
    );
    const candles = (candlesResp.candlesticks ?? candlesResp.candles ?? []).filter(
      (c) => c != null,
    );
    if (!candles.length) return null;

    const series = candles
      .map((c) => {
        const tsSec = (c.end_ts ?? c.start_ts) as number | undefined;
        if (!tsSec) return null;
        const priceCents =
          (c.close_yes as number | undefined) ??
          (c.close as number | undefined) ??
          (c.last_price as number | undefined);
        if (priceCents == null) return null;
        return { t: tsSec * 1000, price: priceCents / 100 };
      })
      .filter((p): p is { t: number; price: number } => p != null);

    return series.length ? series : null;
  } catch {
    return null;
  }
}

function mergeSeries(
  pm: { t: number; mid: number | null }[] | null,
  kalshi: { t: number; price: number }[] | null,
): SeriesRow[] {
  if ((!pm || !pm.length) && (!kalshi || !kalshi.length)) return [];
  const times = new Set<number>();
  const pmSorted = (pm ?? []).slice().sort((a, b) => a.t - b.t);
  const kalshiSorted = (kalshi ?? []).slice().sort((a, b) => a.t - b.t);
  pmSorted.forEach((p) => times.add(p.t));
  kalshiSorted.forEach((k) => times.add(k.t));
  const sortedTimes = Array.from(times).sort((a, b) => a - b);

  const rows: SeriesRow[] = [];
  let pmIdx = 0;
  let kIdx = 0;

  for (const t of sortedTimes) {
    while (pmIdx + 1 < pmSorted.length && pmSorted[pmIdx + 1].t <= t) pmIdx += 1;
    while (kIdx + 1 < kalshiSorted.length && kalshiSorted[kIdx + 1].t <= t) kIdx += 1;

    const row: SeriesRow = { t };
    const pmPoint = pmSorted[pmIdx];
    if (pmPoint && pmPoint.t <= t && pmPoint.mid != null) {
      row.polymarket = pmPoint.mid;
    }
    const kPoint = kalshiSorted[kIdx];
    if (kPoint && kPoint.t <= t) {
      row.kalshi = kPoint.price;
    }
    if (row.polymarket != null || row.kalshi != null) {
      rows.push(row);
    }
  }

  return rows;
}

export default function ComparePairPage({ params }: { params: { pairId: string } }) {
  const pairId = Number(params.pairId);
  const [detail, setDetail] = useState<CompareDetail | null>(null);
  const [pmSeries, setPmSeries] = useState<{ t: number; mid: number | null }[] | null>(null);
  const [kalshiSeries, setKalshiSeries] = useState<{ t: number; price: number }[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!pairId || Number.isNaN(pairId)) return;
    let cancelled = false;

    async function run() {
      try {
        setLoading(true);
        setError(null);
        const d = await fetchJSON<CompareDetail>(`${API}/events/compare/${pairId}`);
        if (cancelled) return;
        setDetail(d);

        const pm = await loadPolymarketSeries(d.polymarket_market_id, d.polymarket_asset_id);
        if (cancelled) return;
        const pmData = pm?.series ?? null;
        setPmSeries(pmData);

        let windowMs: { start: number; end: number } | undefined;
        if (pmData && pmData.length > 1) {
          const times = pmData.map((p) => p.t).sort((a, b) => a - b);
          windowMs = { start: times[0], end: times[times.length - 1] };
        }
        const kalshi = await loadKalshiSeries(d.kalshi_market_ticker, windowMs);
        if (cancelled) return;
        setKalshiSeries(kalshi);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Failed to load comparison');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [pairId]);

  const combined = useMemo(() => mergeSeries(pmSeries, kalshiSeries), [pmSeries, kalshiSeries]);

  const pmTitle =
    detail?.polymarket?.title ||
    detail?.polymarket_market_id ||
    (detail ? `Polymarket ${detail.polymarket_market_id}` : '');
  const kalshiTitle =
    (detail?.kalshi?.title as string | undefined) ||
    (detail?.kalshi?.subtitle as string | undefined) ||
    detail?.kalshi_market_ticker ||
    (detail ? `Kalshi ${detail.kalshi_market_ticker}` : '');

  return (
    <div>
      <h2>Event comparison</h2>
      {detail && (
        <p style={{ color: '#aaa', marginTop: 4, marginBottom: 16 }}>
          {detail.label || 'Curated Polymarket vs Kalshi pair'}
        </p>
      )}
      {loading && <p>Loading comparison…</p>}
      {error && !loading && (
        <div style={{ background: '#3a2020', border: '1px solid #a44', padding: 12, marginBottom: 16, borderRadius: 4 }}>
          <strong style={{ color: '#f88' }}>Error:</strong> {error}
        </div>
      )}
      {detail && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
          <div>
            <strong>Polymarket:</strong>{' '}
            <span>{pmTitle}</span>{' '}
            <span style={{ color: '#777', fontSize: 12 }}>({detail.polymarket_market_id})</span>
          </div>
          <div>
            <strong>Kalshi:</strong>{' '}
            <span>{kalshiTitle}</span>{' '}
            <span style={{ color: '#777', fontSize: 12 }}>({detail.kalshi_market_ticker})</span>
          </div>
        </div>
      )}
      {combined.length > 0 && (
        <ResponsiveContainer width="100%" height={420}>
          <LineChart data={combined} margin={{ top: 8, right: 8, left: 8, bottom: 24 }}>
            <XAxis
              dataKey="t"
              stroke="#888"
              tickFormatter={(t) => new Date(t).toLocaleString(undefined, { hour: '2-digit', minute: '2-digit' })}
            />
            <YAxis domain={[0, 1]} stroke="#888" />
            <Tooltip
              labelFormatter={(t) =>
                new Date(t).toLocaleString(undefined, {
                  hour: '2-digit',
                  minute: '2-digit',
                  month: 'short',
                  day: 'numeric',
                })
              }
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="polymarket"
              stroke="#7dd"
              strokeWidth={2}
              dot={false}
              name="Polymarket (Yes)"
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="kalshi"
              stroke="#d77"
              strokeWidth={2}
              dot={false}
              name="Kalshi (Yes)"
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
      {!loading && combined.length === 0 && (
        <p style={{ color: '#888', marginTop: 16 }}>
          No overlapping price history could be loaded yet for this pair. Ensure you have Polymarket events
          ingested and that Kalshi candlestick data is available for this market.
        </p>
      )}
      <div style={{ marginTop: 24 }}>
        <a href="/events/compare" style={{ color: '#7dd' }}>
          ← Back to event pairs
        </a>
      </div>
    </div>
  );
}

