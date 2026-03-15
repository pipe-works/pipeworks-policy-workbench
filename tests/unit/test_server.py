"""Unit tests for server runtime helpers."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from policy_workbench import server


def test_port_candidates_without_requested_port_covers_range() -> None:
    """Candidate generation should include the entire 8000-range by default."""

    candidates = server._port_candidates(None)
    assert candidates[0] == 8000
    assert candidates[-1] == 8099
    assert len(candidates) == 100


def test_port_candidates_requested_first() -> None:
    """When a preferred port is valid, it should be tested first."""

    candidates = server._port_candidates(8012)
    assert candidates[0] == 8012
    assert sorted(candidates) == list(range(8000, 8100))


def test_port_candidates_rejects_out_of_range_port() -> None:
    """Invalid requested ports should fail fast with clear error messaging."""

    with pytest.raises(ValueError, match="outside supported range"):
        server._port_candidates(9000)


def test_choose_server_port_uses_requested_port_when_available(monkeypatch) -> None:
    """Requested port should be returned directly when available."""

    monkeypatch.setattr(
        "policy_workbench.server.is_port_available", lambda host, port: port == 8033
    )
    selected = server.choose_server_port(host="127.0.0.1", requested_port=8033)
    assert selected == 8033


def test_choose_server_port_falls_back_to_next_available(monkeypatch) -> None:
    """Selection should walk candidate ports until an available one is found."""

    monkeypatch.setattr(
        "policy_workbench.server.is_port_available", lambda host, port: port == 8002
    )
    selected = server.choose_server_port(host="127.0.0.1", requested_port=8000)
    assert selected == 8002


def test_choose_server_port_raises_when_none_available(monkeypatch) -> None:
    """A clear runtime error should be raised when every in-range port is occupied."""

    monkeypatch.setattr("policy_workbench.server.is_port_available", lambda host, port: False)
    with pytest.raises(RuntimeError, match="No available ports"):
        server.choose_server_port(host="127.0.0.1")


def test_build_uvicorn_log_config_adds_prefix() -> None:
    """Formatter string should start with the service identifier prefix."""

    log_config = server.build_uvicorn_log_config(prefix="pol-work-bench")
    default_fmt = log_config["formatters"]["default"]["fmt"]
    assert default_fmt.startswith("pol-work-bench ")
    assert "%(levelprefix)s" in default_fmt


def test_resolve_default_port_from_environment_unset_returns_none(monkeypatch) -> None:
    """Missing env var should preserve first-available port behavior."""

    monkeypatch.delenv(server.DEFAULT_PORT_ENV, raising=False)
    assert server.resolve_default_port_from_environment() is None


def test_resolve_default_port_from_environment_blank_returns_none(monkeypatch) -> None:
    """Blank env var should preserve first-available port behavior."""

    monkeypatch.setenv(server.DEFAULT_PORT_ENV, "   ")
    assert server.resolve_default_port_from_environment() is None


def test_resolve_default_port_from_environment_parses_valid_port(monkeypatch) -> None:
    """Valid integer in supported range should be returned."""

    monkeypatch.setenv(server.DEFAULT_PORT_ENV, "8013")
    assert server.resolve_default_port_from_environment() == 8013


def test_resolve_default_port_from_environment_rejects_non_integer(monkeypatch) -> None:
    """Non-integer values should raise an actionable error."""

    monkeypatch.setenv(server.DEFAULT_PORT_ENV, "not-a-number")
    with pytest.raises(ValueError, match="must be an integer"):
        server.resolve_default_port_from_environment()


def test_resolve_default_port_from_environment_rejects_out_of_range(monkeypatch) -> None:
    """Out-of-range values should raise an actionable error."""

    monkeypatch.setenv(server.DEFAULT_PORT_ENV, "9000")
    with pytest.raises(ValueError, match="must be in 8000-8099"):
        server.resolve_default_port_from_environment()


def test_run_server_uses_environment_default_port_when_cli_port_missing(monkeypatch) -> None:
    """run_server should resolve requested port from env when CLI omits --port."""

    captured: dict[str, object] = {}

    def fake_choose_server_port(host: str, requested_port: int | None = None) -> int:
        captured["host"] = host
        captured["requested_port"] = requested_port
        return 8014

    def fake_uvicorn_run(app, **kwargs) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setenv(server.DEFAULT_PORT_ENV, "8014")
    monkeypatch.setattr("policy_workbench.server.choose_server_port", fake_choose_server_port)
    monkeypatch.setattr("policy_workbench.server.create_app", lambda: "asgi-app")
    monkeypatch.setattr(
        "policy_workbench.server.build_uvicorn_log_config",
        lambda prefix: {"prefix": prefix},
    )
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=fake_uvicorn_run))

    server.run_server(host="127.0.0.1", requested_port=None)

    assert captured["requested_port"] == 8014
    assert captured["port"] == 8014


def test_run_server_cli_port_overrides_environment_default(monkeypatch) -> None:
    """Explicit CLI --port should win over env-provided default port."""

    captured: dict[str, object] = {}

    def fake_choose_server_port(host: str, requested_port: int | None = None) -> int:
        captured["requested_port"] = requested_port
        return 8007

    monkeypatch.setenv(server.DEFAULT_PORT_ENV, "8014")
    monkeypatch.setattr("policy_workbench.server.choose_server_port", fake_choose_server_port)
    monkeypatch.setattr("policy_workbench.server.create_app", lambda: "asgi-app")
    monkeypatch.setattr(
        "policy_workbench.server.build_uvicorn_log_config",
        lambda prefix: {"prefix": prefix},
    )
    monkeypatch.setitem(
        sys.modules,
        "uvicorn",
        SimpleNamespace(run=lambda app, **kwargs: None),
    )

    server.run_server(host="127.0.0.1", requested_port=8007)

    assert captured["requested_port"] == 8007
