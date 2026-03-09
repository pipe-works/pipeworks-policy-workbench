"""Server runtime helpers for the policy workbench web app.

This module keeps server concerns isolated from the CLI entrypoint so the CLI
stays thin and testable. It provides three responsibilities:

1. Deterministically choose an available port in the 8000-range.
2. Build a Uvicorn logging configuration that prefixes INFO output.
3. Create and run the ASGI application.
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from typing import Any, cast

PORT_RANGE_START = 8000
PORT_RANGE_END = 8099
DEFAULT_HOST = "0.0.0.0"
DEFAULT_LOG_PREFIX = "pol-work-bench"


def _port_candidates(requested_port: int | None) -> list[int]:
    """Return deterministic candidate ports within the supported 8000-range.

    The requested port is tried first (when provided and valid), followed by the
    rest of the range in ascending order. This preserves caller intent without
    giving up auto-recovery when that specific port is occupied.
    """

    supported_ports = list(range(PORT_RANGE_START, PORT_RANGE_END + 1))
    if requested_port is None:
        return supported_ports

    if requested_port not in supported_ports:
        raise ValueError(
            f"Requested port {requested_port} is outside supported range "
            f"{PORT_RANGE_START}-{PORT_RANGE_END}."
        )

    return [requested_port] + [port for port in supported_ports if port != requested_port]


def is_port_available(host: str, port: int) -> bool:
    """Return ``True`` when the target host/port can be bound by this process."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def choose_server_port(host: str, requested_port: int | None = None) -> int:
    """Choose an unused server port within ``8000-8099``.

    Args:
        host: Host interface the server will bind to.
        requested_port: Optional preferred port in ``8000-8099``.

    Returns:
        The first available candidate port.

    Raises:
        RuntimeError: If no available ports are found in the supported range.
        ValueError: If a requested port is outside the supported range.
    """

    for candidate in _port_candidates(requested_port):
        if is_port_available(host, candidate):
            return candidate

    raise RuntimeError(
        f"No available ports found in supported range {PORT_RANGE_START}-{PORT_RANGE_END}."
    )


def build_uvicorn_log_config(prefix: str = DEFAULT_LOG_PREFIX) -> dict[str, Any]:
    """Build Uvicorn logging config with a static service prefix.

    Uvicorn's default formatter already renders ``INFO:`` style level prefixes.
    This function prepends an additional service identifier to make tmux panes
    easy to distinguish when multiple Pipe-Works services run simultaneously.
    """

    cleaned_prefix = prefix.strip()
    formatted_prefix = f"{cleaned_prefix} " if cleaned_prefix else ""

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": f"{formatted_prefix}%(levelprefix)s %(message)s",
                "use_colors": None,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": (
                    f"{formatted_prefix}%(levelprefix)s "
                    '%(client_addr)s - "%(request_line)s" %(status_code)s'
                ),
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stderr",
            },
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "access",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }


def create_app() -> Callable[..., Any]:
    """Create the ASGI app instance.

    The primary implementation uses FastAPI when available. If FastAPI is not
    installed yet, this function returns a tiny standards-compliant ASGI app so
    local ``pw-policy serve`` remains usable during early scaffolding.
    """

    try:
        from fastapi import FastAPI  # type: ignore[import-not-found]
    except ImportError:

        async def fallback_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
            """Fallback ASGI app returning plain-text health output."""

            if scope["type"] != "http":
                return

            body = b"policy-workbench alive\n"
            headers = [(b"content-type", b"text/plain; charset=utf-8")]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            await send({"type": "http.response.body", "body": body})

        return fallback_app

    app = FastAPI(title="Pipeworks Policy Workbench", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Simple readiness endpoint for local runtime checks."""

        return {"status": "ok"}

    return cast(Callable[..., Any], app)


def run_server(
    host: str = DEFAULT_HOST,
    requested_port: int | None = None,
    log_prefix: str = DEFAULT_LOG_PREFIX,
) -> None:
    """Run the policy workbench server with 8000-range port auto-selection."""

    try:
        import uvicorn  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "uvicorn is required to run the server. Install with `pyenv exec pip install uvicorn`."
        ) from exc

    selected_port = choose_server_port(host=host, requested_port=requested_port)
    uvicorn.run(
        create_app(),
        host=host,
        port=selected_port,
        log_level="info",
        log_config=build_uvicorn_log_config(prefix=log_prefix),
    )
