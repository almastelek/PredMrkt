"""TOML config loading and profiles."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

# Default config search path (project root or cwd)
_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config"
_CWD_CONFIG = Path.cwd() / "config"


def _load_toml(path: Path) -> dict[str, Any]:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base. Override values take precedence."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _find_config_dir() -> Path:
    if _CWD_CONFIG.exists():
        return _CWD_CONFIG
    return _CONFIG_DIR


def load_config(profile: str | None = None) -> dict[str, Any]:
    """Load merged config from default.toml and optional profile overlay."""
    config_dir = _find_config_dir()
    default_path = config_dir / "default.toml"
    if not default_path.exists():
        return {}
    base = _load_toml(default_path)
    if profile:
        profile_path = config_dir / f"{profile}.toml"
        if profile_path.exists():
            overlay = _load_toml(profile_path)
            base = _deep_merge(base, overlay)
    return base


def get_settings(profile: str | None = None) -> Settings:
    """Return Settings instance from merged config."""
    raw = load_config(profile)
    return Settings.from_dict(raw)


class Settings:
    """Application settings from TOML config."""

    def __init__(
        self,
        *,
        ingestion: dict[str, Any] | None = None,
        storage: dict[str, Any] | None = None,
        markets: dict[str, Any] | None = None,
        polymarket: dict[str, Any] | None = None,
        logging: dict[str, Any] | None = None,
    ):
        self.ingestion = ingestion or {}
        self.storage = storage or {}
        self.markets = markets or {}
        self.polymarket = polymarket or {}
        self.logging = logging or {}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Settings:
        return cls(
            ingestion=raw.get("ingestion"),
            storage=raw.get("storage"),
            markets=raw.get("markets"),
            polymarket=raw.get("polymarket"),
            logging=raw.get("logging"),
        )

    # Convenience accessors with defaults
    @property
    def db_path(self) -> str:
        return self.storage.get("db_path", "data/predex.duckdb")

    @property
    def event_batch_size(self) -> int:
        return int(self.storage.get("event_batch_size", 100))

    @property
    def reconnect_base_delay_sec(self) -> float:
        return float(self.ingestion.get("reconnect_base_delay_sec", 1.0))

    @property
    def reconnect_max_delay_sec(self) -> float:
        return float(self.ingestion.get("reconnect_max_delay_sec", 60.0))

    @property
    def reconnect_max_retries(self) -> int:
        return int(self.ingestion.get("reconnect_max_retries", 0))

    @property
    def discovery_refresh_interval_sec(self) -> int:
        return int(self.ingestion.get("discovery_refresh_interval_sec", 600))

    @property
    def track_count(self) -> int:
        return int(self.markets.get("track_count", 50))

    @property
    def min_volume_24h(self) -> float:
        return float(self.markets.get("min_volume_24h", 0))

    @property
    def min_liquidity(self) -> float:
        return float(self.markets.get("min_liquidity", 0))

    @property
    def category_allowlist(self) -> list[str]:
        return list(self.markets.get("category_allowlist") or [])

    @property
    def category_denylist(self) -> list[str]:
        return list(self.markets.get("category_denylist") or [])

    @property
    def pinned_markets(self) -> list[str]:
        return list(self.markets.get("pinned_markets") or [])

    @property
    def gamma_api_base(self) -> str:
        return self.polymarket.get("gamma_api_base", "https://gamma-api.polymarket.com")

    @property
    def clob_ws_url(self) -> str:
        return self.polymarket.get(
            "clob_ws_url", "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        )

    @property
    def logging_level(self) -> str:
        return self.logging.get("level", "INFO").upper()

    @property
    def logging_format(self) -> str:
        return self.logging.get("format", "console")

    @property
    def logging_level_num(self) -> int:
        return getattr(logging, self.logging_level, logging.INFO)


def configure_logging(settings: Settings) -> None:
    """Configure structlog with settings. Call once at application entry."""
    import structlog

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if settings.logging_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(settings.logging_level_num),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
