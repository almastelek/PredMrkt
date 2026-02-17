'use client';

import { useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

export default function MarketsPage() {
  const [markets, setMarkets] = useState<{ market_id?: string; title?: string; volume_24h?: number }[]>([]);

  useEffect(() => {
    fetch(`${API}/markets?tracked_only=true`)
      .then((r) => r.json())
      .then(setMarkets)
      .catch(() => setMarkets([]));
  }, []);

  return (
    <div>
      <h2>Tracked Markets</h2>
      <ul style={{ listStyle: 'none', padding: 0 }}>
        {markets.slice(0, 20).map((m, i) => (
          <li key={m.market_id ?? i} style={{ padding: '8px 0', borderBottom: '1px solid #333' }}>
            {(m.title || m.market_id || '').slice(0, 60)} — vol: {m.volume_24h ?? 0}
          </li>
        ))}
      </ul>
      <p>{markets.length} total</p>
    </div>
  );
}
