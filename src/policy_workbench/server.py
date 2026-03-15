"""Server runtime helpers for the policy workbench web app.

This module keeps server concerns isolated from the CLI entrypoint so the CLI
stays thin and testable. It provides three responsibilities:

1. Deterministically choose an available port in the 8000-range.
2. Build a Uvicorn logging configuration that prefixes INFO output.
3. Create and run the ASGI application.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Callable
from typing import Any, cast

PORT_RANGE_START = 8000
PORT_RANGE_END = 8099
DEFAULT_HOST = "0.0.0.0"
DEFAULT_LOG_PREFIX = "pol-work-bench"
DEFAULT_PORT_ENV = "PW_POLICY_DEFAULT_PORT"


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


def resolve_default_port_from_environment() -> int | None:
    """Return optional default serve port from environment.

    ``PW_POLICY_DEFAULT_PORT`` semantics:
    - unset/blank: no preferred port (use first available in range)
    - integer in 8000-8099: preferred default port
    """

    raw_port = os.getenv(DEFAULT_PORT_ENV)
    if raw_port is None:
        return None

    normalized = raw_port.strip()
    if not normalized:
        return None

    try:
        port = int(normalized)
    except ValueError as exc:
        raise ValueError(
            f"{DEFAULT_PORT_ENV} must be an integer in {PORT_RANGE_START}-{PORT_RANGE_END}, "
            f"got {raw_port!r}."
        ) from exc

    if port < PORT_RANGE_START or port > PORT_RANGE_END:
        raise ValueError(
            f"{DEFAULT_PORT_ENV} must be in {PORT_RANGE_START}-{PORT_RANGE_END}, got {port}."
        )

    return port


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

    The primary implementation delegates to ``policy_workbench.web_app``.
    If web dependencies are not installed yet, this function returns a tiny
    standards-compliant ASGI app so ``pw-policy serve`` remains usable.
    """

    try:
        from .web_app import create_web_app
    except ImportError:
        return _create_fallback_app()

    return cast(Callable[..., Any], create_web_app())


def _create_fallback_app() -> Callable[..., Any]:
    """Return minimal fallback ASGI app used when FastAPI stack is unavailable."""

    async def fallback_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        """Fallback ASGI app returning plain-text health output."""

        if scope["type"] != "http":
            return

        body = b"policy-workbench alive\n"
        headers = [(b"content-type", b"text/plain; charset=utf-8")]
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    return fallback_app


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

    resolved_requested_port = (
        requested_port if requested_port is not None else resolve_default_port_from_environment()
    )
    selected_port = choose_server_port(host=host, requested_port=resolved_requested_port)
    uvicorn.run(
        create_app(),
        host=host,
        port=selected_port,
        log_level="info",
        log_config=build_uvicorn_log_config(prefix=log_prefix),
    )
