"""Runtime flags for the API process (set by run_api, read by routers)."""

from __future__ import annotations

run_with_ingestion: bool = False
run_with_sports: bool = False
config_profile: str | None = None

# Startup behavior (only applied when running with in-process ingestion)
refresh_markets_metadata_on_start: bool = True
refresh_tracked_on_start: bool = False

# Optional whales background ingestion (only when run_with_ingestion=True)
run_with_whales: bool = False
whales_interval_sec: int = 300
whales_min_cash: float | None = None
whales_page_limit: int | None = None
whales_max_pages: int | None = None
whales_taker_only: bool = True

