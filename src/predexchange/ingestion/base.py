"""Abstract connector protocol for pluggable venues (Polymarket, Kalshi, ...)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Protocol


class MarketDiscoveryProtocol(Protocol):
    """Protocol for market discovery (REST)."""

    def fetch_markets(self, limit: int = 100, **kwargs: Any) -> list[Any]: ...
    def normalize_market(self, raw: dict[str, Any]) -> Any: ...


class WSStreamProtocol(Protocol):
    """Protocol for WebSocket streaming."""

    async def stream_events(
        self,
        asset_ids: list[str],
        on_message: Any,
        **kwargs: Any,
    ) -> None: ...


class VenueConnector(ABC):
    """Abstract venue connector: discovery + WS stream. Implement for each exchange."""

    venue_id: str = ""

    @abstractmethod
    def discover_markets(self, limit: int = 100, **kwargs: Any) -> list[Any]:
        """Return list of canonical Market models."""
        ...

    @abstractmethod
    async def run_ingestion(
        self,
        asset_ids: list[str],
        on_message: Any,
        **kwargs: Any,
    ) -> None:
        """Run WebSocket ingestion, calling on_message(payload, ingest_ts) for each event."""
        ...
