'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

type SimRun = {
  run_id?: string;
  strategy_name?: string;
  market_id?: string;
  events_processed?: number;
  fill_count?: number;
  realized_pnl?: number;
  final_inventory?: number;
  params?: Record<string, unknown>;
};

export default function SimRunDetailPage() {
  const params = useParams();
  const id = params?.id as string;
  const [run, setRun] = useState<SimRun | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!id) return;
    setNotFound(false);
    fetch(`${API}/sim/runs/${encodeURIComponent(id)}`)
      .then((r) => {
        if (!r.ok) {
          if (r.status === 404) setNotFound(true);
          return null;
        }
        return r.json();
      })
      .then((data) => setRun(data))
      .catch(() => setRun(null));
  }, [id]);

  if (notFound) return <p style={{ color: '#c66' }}>Run not found. Check the ID or run a simulation: <code>predex sim run --strategy mm_basic --market &lt;condition_id&gt;</code></p>;
  if (!run) return <p>Loading…</p>;

  return (
    <div style={{ maxWidth: 640 }}>
      <h2 style={{ marginTop: 0 }}>Run {run.run_id}</h2>
      <p><strong>Strategy:</strong> {run.strategy_name}</p>
      <p>
        <strong>Event:</strong>{' '}
        {run.market_id ? (
          <a href={`/markets/${encodeURIComponent(run.market_id)}`} style={{ color: '#7dd' }}>
            {run.market_id.slice(0, 20)}…
          </a>
        ) : (
          run.market_id
        )}
      </p>
      <p><strong>Events processed:</strong> {run.events_processed} · <strong>Fills:</strong> {run.fill_count}</p>
      <p><strong>Realized PnL:</strong> {run.realized_pnl} · <strong>Final inventory:</strong> {run.final_inventory}</p>
      {run.params && Object.keys(run.params).length > 0 && (
        <div style={{ marginTop: 16 }}>
          <strong>Params</strong>
          <pre style={{ background: '#1a1a1a', padding: 12, borderRadius: 6, overflow: 'auto', fontSize: 13 }}>
            {JSON.stringify(run.params, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
