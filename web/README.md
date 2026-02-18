# PredExchange Web Dashboard

1. From project root, run **one** of:
   - **Single command (recommended):** `predex api --with-ingestion` — API and WebSocket ingestion in one process (no DB lock issues).
   - Or API only: `predex api` (run `predex track start` in another terminal for live data; DuckDB allows only one writer process, so API and track start in separate processes can conflict).
2. Run the frontend: `cd web && npm install && npm run dev`
3. Open http://localhost:3000

Set `NEXT_PUBLIC_API=http://127.0.0.1:8000` if the API runs elsewhere.
