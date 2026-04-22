"""API server command."""

import typer

from predexchange.api.main import run_api

app = typer.Typer(help="Start API server for web dashboard")


@app.callback(invoke_without_command=True)
def api(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    with_ingestion: bool = typer.Option(
        False, "--with-ingestion", help="Run CLOB + Sports WebSocket ingestion in the same process",
    ),
    with_sports: bool = typer.Option(
        False, "--with-sports", help="Run only Sports WebSocket (live scores). Implied by --with-ingestion.",
    ),
    refresh_tracked: bool = typer.Option(
        False,
        "--refresh-tracked",
        help="On startup (with --with-ingestion), refresh tracked markets via Gamma selector (like 'predex markets discover')",
    ),
    with_whales: bool = typer.Option(
        False,
        "--with-whales",
        help="Run whales Data API ingestion in a background loop (requires --with-ingestion)",
    ),
    whales_interval_sec: int | None = typer.Option(
        None,
        "--whales-interval-sec",
        help="Background whales ingest interval (seconds). Default from config.",
    ),
    whales_min_cash: float | None = typer.Option(
        None,
        "--whales-min-cash",
        help="Background whales min cash filter. Default from config.",
    ),
    whales_page_limit: int | None = typer.Option(
        None,
        "--whales-page-limit",
        help="Background whales page limit for /trades. Default from config.",
    ),
    whales_max_pages: int | None = typer.Option(
        None,
        "--whales-max-pages",
        help="Background whales max pages per cycle. Default from config.",
    ),
    with_signals: bool = typer.Option(
        False,
        "--with-signals",
        help="Run signals pipeline (episodes -> stats -> alerts) periodically. "
             "Can also be enabled via [signals].enabled_background in config.",
    ),
    signals_interval_sec: int | None = typer.Option(
        None,
        "--signals-interval-sec",
        help="Signals pipeline cycle interval (seconds). Default from [signals].background_interval_sec.",
    ),
    profile: str | None = typer.Option(None, "--profile", help="Config profile (e.g. dev)"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    run_api(
        host=host,
        port=port,
        with_ingestion=with_ingestion,
        with_sports=with_sports,
        profile=profile,
        refresh_tracked=refresh_tracked,
        with_whales=with_whales,
        whales_interval_sec=whales_interval_sec,
        whales_min_cash=whales_min_cash,
        whales_page_limit=whales_page_limit,
        whales_max_pages=whales_max_pages,
        with_signals=with_signals,
        signals_interval_sec=signals_interval_sec,
    )


if __name__ == "__main__":
    app()
