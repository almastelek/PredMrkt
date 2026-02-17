"""Kalshi REST/WS client stub. Implement with Kalshi API when ready."""

from __future__ import annotations

from typing import Any

from predexchange.ingestion.base import VenueConnector
from predexchange.models import Market


class KalshiConnector(VenueConnector):
    """Kalshi connector - stub. Add WS ingestion, raw event log, normalization to canonical schema."""

    venue_id = "kalshi"

    def discover_markets(self, limit: int = 100, **kwargs: Any) -> list[Market]:
        # TODO: Kalshi REST market list -> canonical Market
        return []

    async def run_ingestion(
        self,
        asset_ids: list[str],
        on_message: Any,
        **kwargs: Any,
    ) -> None:
        # TODO: Kalshi WebSocket subscribe, on_message callback
        raise NotImplementedError("Kalshi ingestion not implemented yet")
