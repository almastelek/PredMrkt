'use client';

import { useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

export default function Home() {
  const [health, setHealth] = useState<{ status?: string } | null>(null);
  const [stats, setStats] = useState<{ total_events?: number } | null>(null);

  useEffect(() => {
    fetch(`${API}/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ status: 'error' }));
    fetch(`${API}/events/stats`)
      .then((r) => r.json())
      .then(setStats)
      .catch(() => setStats(null));
  }, []);

  return (
    <div>
      <p>Status: {health?.status ?? 'loading...'}</p>
      <p>Total events in log: {stats?.total_events ?? '-'}</p>
    </div>
  );
}
