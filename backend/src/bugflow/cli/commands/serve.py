"""`bugflow serve`: start the HTTP API."""

from __future__ import annotations

import ipaddress
import signal
from typing import Annotated, Any

import typer
import uvicorn

from bugflow.api.app import create_app
from bugflow.cli.context import bootstrap
from bugflow.cli.output import echo, echo_error, guarded

NO_AUTH_WARNING = "Warning: the API has no authentication; do not expose it beyond this machine"


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _exit_cleanly(signum: int, frame: Any) -> None:
    # uvicorn re-raises the signal after a graceful stop; a requested stop is a clean exit.
    raise SystemExit(0)


def _install_term_handler() -> Any:
    try:
        return signal.signal(signal.SIGTERM, _exit_cleanly)
    except ValueError:  # not the main thread
        return None


def _restore_term_handler(previous: Any) -> None:
    if previous is not None:
        signal.signal(signal.SIGTERM, previous)


@guarded
def serve(
    host: Annotated[
        str | None, typer.Option("--host", help="Address to bind (default: API_HOST).")
    ] = None,
    port: Annotated[
        int | None, typer.Option("--port", help="Port to listen on (default: API_PORT).")
    ] = None,
) -> None:
    context = bootstrap()
    try:
        bind_host = host if host is not None else context.settings.api_host
        bind_port = port if port is not None else context.settings.api_port
        echo(f"Serving BugFlow API on http://{bind_host}:{bind_port} (docs at /docs)")
        if not is_loopback(bind_host):
            echo_error(NO_AUTH_WARNING)
        app = create_app(context.settings, context.engine)
        previous = _install_term_handler()
        try:
            uvicorn.run(
                app,
                host=bind_host,
                port=bind_port,
                log_level=context.settings.log_level.lower(),
            )
        except KeyboardInterrupt:
            pass
        finally:
            _restore_term_handler(previous)
    finally:
        context.close()


def register(app: typer.Typer) -> None:
    app.command("serve", help="Start the BugFlow API server.")(serve)
