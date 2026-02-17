'use client';

import { useEffect, useState } from 'react';

const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

export default function SimRunsPage() {
  const [runs, setRuns] = useState<string[]>([]);

  useEffect(() => {
    fetch(`${API}/sim/runs`)
      .then((r) => r.json())
      .then(setRuns)
      .catch(() => setRuns([]));
  }, []);

  return (
    <div>
      <h2>Simulation Runs</h2>
      <ul style={{ listStyle: 'none', padding: 0 }}>
        {runs.map((id) => (
          <li key={id}>
            <a href={`/sim/${id}`} style={{ color: '#7dd' }}>{id}</a>
          </li>
        ))}
      </ul>
      {runs.length === 0 && <p>No runs yet. Use: predex sim run --strategy mm_basic --market &lt;id&gt;</p>}
    </div>
  );
}
