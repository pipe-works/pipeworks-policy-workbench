"""Unit tests for explicit policy workbench runtime source modes."""

from __future__ import annotations

import pytest

from policy_workbench import runtime_mode


def test_default_runtime_mode_is_offline_local_disk() -> None:
    """Runtime mode should default to offline local-disk profile."""
    state = runtime_mode.get_runtime_mode()
    assert state.mode_key == "offline"
    assert state.source_kind == "local_disk"
    assert state.active_server_url is None
    assert {option.mode_key for option in state.options} == {
        "offline",
        "server_dev",
        "server_prod",
    }


def test_offline_mode_disables_server_api_url_resolution() -> None:
    """Offline mode should fail closed for server-only API operations."""
    runtime_mode.set_runtime_mode(mode_key="offline", server_url=None)
    state = runtime_mode.get_runtime_mode()
    assert state.mode_key == "offline"
    assert state.source_kind == "local_disk"
    assert state.active_server_url is None

    with pytest.raises(runtime_mode.RuntimeModeUnavailableError, match="Offline mode active"):
        runtime_mode.require_server_api_url()


def test_server_mode_requires_absolute_http_or_https_url() -> None:
    """Editable server modes should reject unsupported URL values."""
    with pytest.raises(ValueError, match="absolute http\\(s\\)"):
        runtime_mode.set_runtime_mode(mode_key="server_dev", server_url="mud.example.test")

    with pytest.raises(ValueError, match="absolute http\\(s\\)"):
        runtime_mode.set_runtime_mode(mode_key="server_dev", server_url="ftp://mud.example.test")


def test_server_mode_set_and_require_url_normalizes_trailing_slash() -> None:
    """Runtime mode should store normalized API base URL overrides."""
    state = runtime_mode.set_runtime_mode(
        mode_key="server_dev",
        server_url="https://dev.example.test/",
    )
    assert state.mode_key == "server_dev"
    assert state.source_kind == "server_api"
    assert state.active_server_url == "https://dev.example.test"
    assert runtime_mode.require_server_api_url() == "https://dev.example.test"


def test_unknown_mode_key_raises_value_error() -> None:
    """Only declared mode keys should be accepted by runtime-mode setter."""
    with pytest.raises(ValueError, match="Unknown runtime mode"):
        runtime_mode.set_runtime_mode(mode_key="server_stage", server_url=None)


def test_reset_uses_environment_startup_mode_and_defaults(monkeypatch) -> None:
    """Environment defaults should seed reset state for startup mode and URLs."""
    monkeypatch.setenv("PW_POLICY_SOURCE_MODE", "offline")
    monkeypatch.setenv("PW_POLICY_DEV_MUD_API_BASE_URL", "http://127.0.0.1:8123/")
    monkeypatch.setenv("PW_POLICY_PROD_MUD_API_BASE_URL", "https://prod.example.test/")
    runtime_mode._reset_runtime_mode_for_tests()

    state = runtime_mode.get_runtime_mode()
    assert state.mode_key == "offline"
    assert state.source_kind == "local_disk"

    prod_state = runtime_mode.set_runtime_mode(mode_key="server_prod", server_url=None)
    assert prod_state.active_server_url == "https://prod.example.test"

    dev_state = runtime_mode.set_runtime_mode(mode_key="server_dev", server_url=None)
    assert dev_state.active_server_url == "http://127.0.0.1:8123"


def test_legacy_mode_aliases_resolve_to_three_mode_model() -> None:
    """Historical mode keys should normalize to dev/prod internally."""
    dev_state = runtime_mode.set_runtime_mode(mode_key="server_local", server_url=None)
    assert dev_state.mode_key == "server_dev"

    dev_remote_state = runtime_mode.set_runtime_mode(mode_key="server_remote_dev", server_url=None)
    assert dev_remote_state.mode_key == "server_dev"

    prod_state = runtime_mode.set_runtime_mode(mode_key="server_remote_prod", server_url=None)
    assert prod_state.mode_key == "server_prod"
