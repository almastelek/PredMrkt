"""TUI dashboard command."""

import typer

from predexchange.tui.app import run_tui

app = typer.Typer(help="Launch TUI dashboard")


@app.callback(invoke_without_command=True)
def tui(ctx: typer.Context) -> None:
    """Launch the Textual TUI dashboard (live orderbooks + health)."""
    if ctx.invoked_subcommand is not None:
        return
    settings = ctx.obj["settings"]
    run_tui(settings)
