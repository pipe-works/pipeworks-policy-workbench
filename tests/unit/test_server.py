"""Unit tests for server runtime helpers."""

from __future__ import annotations

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
