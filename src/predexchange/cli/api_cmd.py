"""API server command."""

import typer

from predexchange.api.main import run_api

app = typer.Typer(help="Start API server for web dashboard")


@app.callback(invoke_without_command=True)
def api(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    run_api(host=host, port=port)


if __name__ == "__main__":
    app()
