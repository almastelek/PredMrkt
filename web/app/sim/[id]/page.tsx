'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

export default function SimRunDetailPage() {
  const params = useParams();
  const id = params?.id as string;
  const [run, setRun] = useState<{
    run_id?: string;
    strategy_name?: string;
    market_id?: string;
    events_processed?: number;
    fill_count?: number;
    realized_pnl?: number;
    final_inventory?: number;
  } | null>(null);

  useEffect(() => {
    if (!id) return;
    fetch(`${API}/sim/runs/${id}`)
      .then((r) => r.json())
      .then(setRun)
      .catch(() => setRun(null));
  }, [id]);

  if (!run) return <p>Loading or not found...</p>;
  return (
    <div>
      <h2>Run {run.run_id}</h2>
      <p>Strategy: {run.strategy_name}</p>
      <p>Market: {run.market_id}</p>
      <p>Events: {run.events_processed}  Fills: {run.fill_count}</p>
      <p>Realized PnL: {run.realized_pnl}  Final inventory: {run.final_inventory}</p>
    </div>
  );
}
