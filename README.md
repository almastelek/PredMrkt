# PredExchange

Prediction market data, visualization, replay, and simulation platform (Polymarket-first).

## Setup

Requires Python 3.12+.

```bash
uv sync
uv run predex --help
```

## Commands

- `predex markets discover` - Fetch market metadata from Polymarket
- `predex markets list` - List cached markets
- `predex track start [-n N]` - Start ingestion (WebSocket + event log)
- `predex track status` - Connection health and msg/sec
- `predex track stop` - Stop ingestion
- `predex log stats` - Event log statistics
- `predex log export` - Export events to Parquet
- `predex replay run` - Deterministic replay (Phase 3)
- `predex sim run` - Run strategy in simulation (Phase 4)

## Config

Configuration is in `config/default.toml`. Override with a profile: `config/dev.toml` when using `--profile dev`.
