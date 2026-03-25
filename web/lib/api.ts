const API = process.env.NEXT_PUBLIC_API || 'http://127.0.0.1:8000';

export async function getJSON<T>(path: string): Promise<T> {
  const url = path.startsWith('http') ? path : `${API}${path.startsWith('/') ? '' : '/'}${path}`;
  const r = await fetch(url);
  if (!r.ok) {
    const text = await r.text().catch(() => '');
    throw new Error(`HTTP ${r.status} for ${url}${text ? `: ${text.slice(0, 200)}` : ''}`);
  }
  return (await r.json()) as T;
}

export async function sendJSON<T>(
  path: string,
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  body?: unknown,
): Promise<T> {
  const url = `${API}${path.startsWith('/') ? '' : '/'}${path}`;
  const r = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) {
    const text = await r.text().catch(() => '');
    throw new Error(`HTTP ${r.status} for ${url}${text ? `: ${text.slice(0, 200)}` : ''}`);
  }
  return (await r.json()) as T;
}

