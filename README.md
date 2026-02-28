# PredExchange

Prediction market data, visualization, replay, and simulation platform (Polymarket-first).

**Terminology:** An **event** is one prediction question (e.g. “Will X win?”). A **market** is a tradable outcome (e.g. Yes/No for that question). The API uses `market_id` for the event (condition) and `asset_id` for the outcome token.

## Setup

Requires Python 3.12+.

```bash
uv sync
uv run predex --help
```

## Running the stack

1. **API** (required for the web app):
   ```bash
   uv run predex api
   ```
   With live ingestion in the same process (recommended for local dev):
   ```bash
   uv run predex api --with-ingestion
   ```
   API docs: **http://127.0.0.1:8000/docs** (Swagger) and **http://127.0.0.1:8000/redoc**.

2. **Web app** (from project root):
   ```bash
   cd web && npm install && npm run dev
   ```
   Open http://localhost:3000. Set `NEXT_PUBLIC_API` if the API runs elsewhere (e.g. `NEXT_PUBLIC_API=http://localhost:8000`).

3. **One-time discovery** so the API has market metadata and tracked list:
   ```bash
   uv run predex markets discover
   ```
   Then use `predex track start` (or `predex api --with-ingestion`) to ingest live order book data.

## Commands

- `predex markets discover` - Fetch market metadata from Polymarket (Gamma)
- `predex markets list` - List cached markets
- `predex track start [-n N]` - Start ingestion (WebSocket + event log)
- `predex track status` - Connection health and msg/sec
- `predex track stop` - Stop ingestion
- `predex log stats` - Event log statistics
- `predex log export` - Export events to Parquet
- `predex replay run` - Deterministic replay
- `predex sim run` - Run strategy in simulation
- `predex api [--with-ingestion] [--with-sports] [--profile dev]` - Start API server. `--with-ingestion` runs CLOB + Sports WS; `--with-sports` runs only Sports WS (live scores).

## Config

Configuration is in `config/default.toml`. Override with a profile: `config/dev.toml` when using `--profile dev`.
