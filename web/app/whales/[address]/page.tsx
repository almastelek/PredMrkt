'use client';

import { useEffect, useState } from 'react';
import { getJSON, sendJSON } from '../../../lib/api';
const moneyFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
const intFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

function toArray(v: unknown): any[] {
  if (Array.isArray(v)) return v;
  if (v && typeof v === 'object') {
    const obj = v as Record<string, unknown>;
    for (const k of ['positions', 'data', 'items', 'activity', 'results']) {
      if (Array.isArray(obj[k])) return obj[k] as any[];
    }
  }
  return [];
}

function getTitle(item: Record<string, any>): string {
  return (
    item.title ||
    item.marketTitle ||
    item.question ||
    item.eventTitle ||
    item.market_slug ||
    item.slug ||
    item.eventSlug ||
    item.conditionId ||
    item.condition_id ||
    'Unknown market/event'
  );
}

function getMoney(item: Record<string, any>): number | null {
  const keys = ['usdcSize', 'notional_usdc', 'sizeUsd', 'value', 'amount', 'amountUsd', 'pnl', 'realizedPnl'];
  for (const k of keys) {
    const v = item[k];
    if (v != null && !Number.isNaN(Number(v))) return Number(v);
  }
  return null;
}

function getWager(item: Record<string, any>): number | null {
  const keys = ['usdcSize', 'wager', 'wagerUsd', 'amountUsd', 'initialValue', 'costBasis', 'notional_usdc'];
  for (const k of keys) {
    const v = item[k];
    if (v != null && !Number.isNaN(Number(v))) return Number(v);
  }
  const size = Number(item.size ?? item.quantity ?? item.shares ?? item.positionSize ?? NaN);
  const price = Number(item.price ?? item.avgPrice ?? item.averagePrice ?? item.entryPrice ?? NaN);
  if (!Number.isNaN(size) && !Number.isNaN(price)) return size * price;
  return null;
}

function getSize(item: Record<string, any>): number | null {
  const keys = ['size', 'quantity', 'shares', 'positionSize', 'tokens'];
  for (const k of keys) {
    const v = item[k];
    if (v != null && !Number.isNaN(Number(v))) return Number(v);
  }
  return null;
}

function getPriceProb(item: Record<string, any>): number | null {
  const keys = ['price', 'avgPrice', 'averagePrice', 'entryPrice', 'executionPrice', 'pricePaid'];
  for (const k of keys) {
    const v = item[k];
    if (v != null && !Number.isNaN(Number(v))) {
      const n = Number(v);
      // Normalize if cents-like values appear.
      if (n > 1 && n <= 100) return n / 100;
      return n;
    }
  }
  return null;
}

export default function WhaleWalletPage({ params }: { params: { address: string } }) {
  const address = (params.address || '').toLowerCase();
  const [data, setData] = useState<any>(null);
  const [live, setLive] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    setLoading(true);
    getJSON<any>(`/whales/wallets/${encodeURIComponent(address)}`)
      .then((d) => setData(d))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load wallet'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [address]);

  useEffect(() => {
    let cancelled = false;
    setLive(null);
    setLiveError(null);
    getJSON<any>(`/whales/wallets/${encodeURIComponent(address)}/live`)
      .then((d) => {
        if (!cancelled) setLive(d);
      })
      .catch((e) => {
        if (!cancelled) setLiveError(e instanceof Error ? e.message : 'Failed to load live data');
      });
    return () => {
      cancelled = true;
    };
  }, [address]);

  const tracked = !!data?.tracked;

  const toggleTrack = async () => {
    setBusy(true);
    try {
      if (tracked) {
        await sendJSON(`/whales/track/${encodeURIComponent(address)}`, 'DELETE');
      } else {
        await sendJSON(`/whales/track`, 'POST', { address });
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
        <div style={{ marginBottom: 16, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
          <div style={{ background: '#151515', border: '1px solid #2a2a2a', borderRadius: 8, padding: 10 }}>
            <div style={{ color: '#888', fontSize: 12 }}>30d spend</div>
            <div style={{ fontSize: 18 }}>${moneyFmt.format(Number(data.summary.spend_30d || 0))}</div>
          </div>
          <div style={{ background: '#151515', border: '1px solid #2a2a2a', borderRadius: 8, padding: 10 }}>
            <div style={{ color: '#888', fontSize: 12 }}>7d spend</div>
            <div style={{ fontSize: 18 }}>${moneyFmt.format(Number(data.summary.spend_7d || 0))}</div>
          </div>
          <div style={{ background: '#151515', border: '1px solid #2a2a2a', borderRadius: 8, padding: 10 }}>
            <div style={{ color: '#888', fontSize: 12 }}>1d spend</div>
            <div style={{ fontSize: 18 }}>${moneyFmt.format(Number(data.summary.spend_1d || 0))}</div>
          </div>
          <div style={{ background: '#151515', border: '1px solid #2a2a2a', borderRadius: 8, padding: 10 }}>
            <div style={{ color: '#888', fontSize: 12 }}>Active days</div>
            <div style={{ fontSize: 18 }}>{intFmt.format(Number(data.summary.active_days || 0))}</div>
          </div>
          <div style={{ background: '#151515', border: '1px solid #2a2a2a', borderRadius: 8, padding: 10 }}>
            <div style={{ color: '#888', fontSize: 12 }}>Top market concentration</div>
            <div style={{ fontSize: 18 }}>{(Number(data.summary.top_market_concentration_30d || 0) * 100).toFixed(0)}%</div>
          </div>
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
      <div style={{ marginBottom: 12, background: '#151515', border: '1px solid #2a2a2a', borderRadius: 8, padding: 10 }}>
        <div style={{ color: '#888', fontSize: 12 }}>Portfolio value</div>
        <div style={{ fontSize: 20 }}>
          {(() => {
            const v = live?.value;
            if (typeof v === 'number') return `$${moneyFmt.format(v)}`;
            if (v && typeof v === 'object') {
              const valueNum = Number((v as any).value ?? (v as any).total ?? (v as any).totalValue ?? 0);
              return `$${moneyFmt.format(valueNum)}`;
            }
            return '-';
          })()}
        </div>
      </div>
      {liveError && <p style={{ color: '#f88' }}>{liveError}</p>}

      {[
        { key: 'positions', label: 'Open positions' },
        { key: 'closed_positions', label: 'Closed positions' },
        { key: 'activity', label: 'Recent activity' },
      ].map((section) => {
        const rows = toArray((live as any)?.[section.key]);
        return (
          <div key={section.key} style={{ marginTop: 16 }}>
            <h4 style={{ marginBottom: 10 }}>{section.label}</h4>
            {rows.length === 0 ? (
              <p style={{ color: '#888' }}>No data.</p>
            ) : (
              <div style={{ display: 'grid', gap: 10 }}>
                {rows.slice(0, 50).map((item: any, i: number) => {
                  const title = getTitle(item || {});
                  const amount = getMoney(item || {});
                  const wager = getWager(item || {});
                  const size = getSize(item || {});
                  const priceProb = getPriceProb(item || {});
                  const tsRaw = item?.timestamp ?? item?.time ?? item?.updatedAt ?? item?.createdAt;
                  const ts = tsRaw ? new Date(Number(tsRaw) < 10_000_000_000 ? Number(tsRaw) * 1000 : Number(tsRaw)).toLocaleString() : null;
                  return (
                    <div key={`${section.key}-${i}`} style={{ background: '#151515', border: '1px solid #2a2a2a', borderRadius: 8, padding: 10 }}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>{title}</div>
                      <div style={{ color: '#aaa', fontSize: 13 }}>
                        {[item?.outcome ? `Outcome: ${item.outcome}` : null, item?.side ? `Side: ${item.side}` : null, ts ? `Time: ${ts}` : null]
                          .filter(Boolean)
                          .join('  |  ') || 'No extra details'}
                      </div>
                      {amount != null && (
                        <div style={{ marginTop: 6, color: '#7dd' }}>${moneyFmt.format(amount)}</div>
                      )}
                      <div style={{ marginTop: 6, color: '#c8c8c8', fontSize: 13 }}>
                        {wager != null ? `Wagered: $${moneyFmt.format(wager)}` : 'Wagered: n/a'}
                        {size != null ? `  |  Size: ${intFmt.format(size)}` : ''}
                        {priceProb != null ? `  |  Buy price/prob: ${priceProb.toFixed(3)} (${(priceProb * 100).toFixed(1)}%)` : ''}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

