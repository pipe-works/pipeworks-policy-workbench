"""Unit tests for shared mud API runtime resolver helpers."""

from __future__ import annotations

import pytest

from policy_workbench.mud_api_runtime import resolve_mud_api_runtime_config


def test_resolve_mud_api_runtime_config_prefers_overrides(monkeypatch) -> None:
    """Explicit overrides should win over environment defaults."""

    monkeypatch.setenv("PW_TEST_BASE_URL", "http://env.local:8000/")
    monkeypatch.setenv("PW_TEST_SESSION", "env-session")

    config = resolve_mud_api_runtime_config(
        session_id_override="override-session",
        base_url_override=" https://override.local:9443/ ",
        base_url_env_var="PW_TEST_BASE_URL",
        session_id_env_var="PW_TEST_SESSION",
        default_base_url="http://default.local:8000",
        empty_base_url_error="base url missing",
        missing_session_error="session missing",
    )

    assert config.base_url == "https://override.local:9443"
    assert config.session_id == "override-session"


def test_resolve_mud_api_runtime_config_uses_env_and_default(monkeypatch) -> None:
    """Resolver should use env values and then fallback defaults when needed."""

    monkeypatch.delenv("PW_TEST_BASE_URL", raising=False)
    monkeypatch.setenv("PW_TEST_SESSION", "env-session")

    config = resolve_mud_api_runtime_config(
        session_id_override=None,
        base_url_override=None,
        base_url_env_var="PW_TEST_BASE_URL",
        session_id_env_var="PW_TEST_SESSION",
        default_base_url="http://default.local:8000/",
        empty_base_url_error="base url missing",
        missing_session_error="session missing",
    )
    assert config.base_url == "http://default.local:8000"
    assert config.session_id == "env-session"


def test_resolve_mud_api_runtime_config_rejects_blank_base_url(monkeypatch) -> None:
    """Blank base URL should raise the supplied error string."""

    monkeypatch.setenv("PW_TEST_BASE_URL", "   ")
    monkeypatch.setenv("PW_TEST_SESSION", "env-session")

    with pytest.raises(ValueError, match="base url missing"):
        resolve_mud_api_runtime_config(
            session_id_override=None,
            base_url_override=None,
            base_url_env_var="PW_TEST_BASE_URL",
            session_id_env_var="PW_TEST_SESSION",
            default_base_url="http://default.local:8000",
            empty_base_url_error="base url missing",
            missing_session_error="session missing",
        )


def test_resolve_mud_api_runtime_config_rejects_blank_session(monkeypatch) -> None:
    """Blank session id should raise the supplied error string."""

    monkeypatch.setenv("PW_TEST_BASE_URL", "http://env.local:8000")
    monkeypatch.setenv("PW_TEST_SESSION", "   ")

    with pytest.raises(ValueError, match="session missing"):
        resolve_mud_api_runtime_config(
            session_id_override=None,
            base_url_override=None,
            base_url_env_var="PW_TEST_BASE_URL",
            session_id_env_var="PW_TEST_SESSION",
            default_base_url="http://default.local:8000",
            empty_base_url_error="base url missing",
            missing_session_error="session missing",
        )
