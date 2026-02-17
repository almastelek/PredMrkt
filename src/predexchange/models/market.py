"""Market, Event, Outcome - canonical entities."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Outcome(BaseModel):
    """Single outcome (e.g. Yes/No token) in a market."""

    token_id: str
    name: str
    price: float = Field(..., ge=0, le=1, description="Probability/price in [0, 1]")


class Event(BaseModel):
    """Event grouping one or more markets (Polymarket event)."""

    event_id: str
    title: str
    slug: str | None = None
    markets: list[str] = Field(default_factory=list)  # market_ids


class Market(BaseModel):
    """Canonical market - venue-agnostic."""

    market_id: str
    venue: str = "polymarket"
    condition_id: str | None = None  # Polymarket condition ID
    question: str = ""
    title: str = ""
    category: str | None = None
    volume_24h: float = 0.0
    liquidity: float = 0.0
    active: bool = True
    outcomes: list[Outcome] = Field(default_factory=list)
    exchange_ts: int | None = None  # ms epoch
    last_updated: int | None = None  # ms epoch
    extra: dict[str, Any] = Field(default_factory=dict)
