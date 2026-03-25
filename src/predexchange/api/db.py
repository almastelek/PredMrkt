"""Shared DuckDB connection policy for API routes."""

from __future__ import annotations

from predexchange.api import runtime
from predexchange.config import get_settings
from predexchange.storage.db import get_connection


def get_api_connection(*, read_only_override: bool | None = None):
    """
    Return a DuckDB connection using a consistent configuration.

    DuckDB rejects mixed read_only/read_write connections to the same file in
    the same process. When the API is started with in-process ingestion/sports,
    we must use read_write connections everywhere.
    """
    settings = get_settings(runtime.config_profile)
    if read_only_override is None:
        read_only = not (runtime.run_with_ingestion or runtime.run_with_sports)
    else:
        read_only = bool(read_only_override)
    return get_connection(settings.db_path, read_only=read_only)

