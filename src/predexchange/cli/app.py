"""Root CLI app - entry point and command registration."""

from pathlib import Path

import typer

from predexchange.config import get_settings
from predexchange.config.settings import configure_logging

app = typer.Typer(
    name="predex",
    help="PredExchange - Prediction market data, visualization, replay, and simulation.",
    no_args_is_help=True,
)


def _get_profile_callback() -> str | None:
    return None


@app.callback()
def main(
    ctx: typer.Context,
    config_dir: Path | None = typer.Option(
        None, "--config-dir", "-C", help="Config directory (default: ./config or package config)"
    ),
    profile: str | None = typer.Option(
        None, "--profile", "-p", help="Config profile (e.g. dev) to overlay on default.toml"
    ),
) -> None:
    """Configure logging and store options in context."""
    settings = get_settings(profile)
    configure_logging(settings)
    ctx.obj = {"settings": settings, "config_dir": config_dir, "profile": profile}


# Subcommands registered from other modules
from predexchange.cli import markets, track, log, replay, sim, tui_cmd  # noqa: E402

app.add_typer(markets.app, name="markets")
app.add_typer(track.app, name="track")
app.add_typer(log.app, name="log")
app.add_typer(replay.app, name="replay")
app.add_typer(sim.app, name="sim")
app.add_typer(tui_cmd.app, name="tui")


def run() -> None:
    app()


if __name__ == "__main__":
    run()
