"""Runtime flags for the API process (set by run_api, read by routers)."""

from __future__ import annotations

run_with_ingestion: bool = False
run_with_sports: bool = False
config_profile: str | None = None

# Startup behavior (only applied when running with in-process ingestion)
refresh_markets_metadata_on_start: bool = True
refresh_tracked_on_start: bool = False

