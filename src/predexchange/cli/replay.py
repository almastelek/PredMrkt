"""Replay subcommand: run, list."""

import typer

from predexchange.replay.engine import replay_events, replay_to_mid_series
from predexchange.storage.db import get_connection, init_schema
from predexchange.orderbook.aggregator import OrderBookAggregator

app = typer.Typer(help="Deterministic replay of event log")


def _parse_ts(s: str | None) -> int | None:
    if s is None:
        return None
    try:
        return int(s)
    except ValueError:
        return None


@app.command("run")
def run_replay(
    ctx: typer.Context,
    market: str = typer.Option(..., "--market", "-m", help="Market ID"),
    asset: str | None = typer.Option(None, "--asset", "-a", help="Asset ID (for mid series output)"),
    start: str | None = typer.Option(None, "--start", help="Start time (ms epoch)"),
    end: str | None = typer.Option(None, "--end", help="End time (ms epoch)"),
    speed: str = typer.Option("1x", "--speed", help="Speed multiplier (1x, 10x, 50x) - output only for now"),
) -> None:
    """Run deterministic replay for a market and time window."""
    settings = ctx.obj["settings"]
    conn = get_connection(settings.db_path)
    init_schema(conn)
    start_ts = _parse_ts(start)
    end_ts = _parse_ts(end)
    try:
        if asset:
            series = replay_to_mid_series(conn, market, asset, start_ts=start_ts, end_ts=end_ts)
            typer.echo(f"Replayed {len(series)} events -> {len(series)} mid points")
            for ts, mid in series[:20]:
                typer.echo(f"  {ts}  {mid}")
            if len(series) > 20:
                typer.echo(f"  ... and {len(series) - 20} more")
        else:
            agg = OrderBookAggregator()
            replay_events(conn, agg, market_id=market, start_ts=start_ts, end_ts=end_ts)
            n = len(list(agg.engines().values()))
            typer.echo(f"Replayed into {n} orderbook(s)")
    finally:
        conn.close()


@app.command("list")
def list_runs(ctx: typer.Context) -> None:
    """List replay/simulation runs (placeholder - run tracking in Phase 4)."""
    typer.echo("Run tracking coming in Phase 4. Use 'replay run' to replay now.")
