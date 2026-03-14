"""Unit tests for extracted runtime/auth web service helpers."""

from __future__ import annotations

import pytest

from policy_workbench import web_runtime_services
from policy_workbench.mud_api_runtime import MudApiRuntimeConfig


def test_classify_runtime_auth_probe_error_maps_known_failures() -> None:
    """Runtime auth classification should keep stable UI-facing status mapping."""
    assert web_runtime_services.classify_runtime_auth_probe_error(
        error_detail="Policy API requires admin or superuser role.",
        role_required_detail="Policy API requires admin or superuser role.",
    ) == ("forbidden", "Session is valid but role is not admin/superuser.")

    assert web_runtime_services.classify_runtime_auth_probe_error(
        error_detail="Invalid or expired session",
        role_required_detail="Policy API requires admin or superuser role.",
    ) == ("unauthenticated", "Session is invalid or expired.")

    assert web_runtime_services.classify_runtime_auth_probe_error(
        error_detail="other failure",
        role_required_detail="Policy API requires admin or superuser role.",
    ) == ("error", "other failure")


def test_build_runtime_login_payload_normalizes_and_enforces_roles() -> None:
    """Login helper should reject blank credentials and non-admin roles."""
    with pytest.raises(ValueError, match="Username is required"):
        web_runtime_services.build_runtime_login_payload(
            mode_key="server_dev",
            source_kind="server_api",
            active_server_url="http://mud.local:8000",
            username=" ",
            password="secret",
            base_url_override=None,
            default_base_url="http://127.0.0.1:8000",
            allowed_roles={"admin", "superuser"},
            normalize_base_url=lambda value: str(value or "").strip().rstrip("/"),
            fetch_mud_api_json_anonymous=lambda **_kwargs: {},
        )

    forbidden_payload = web_runtime_services.build_runtime_login_payload(
        mode_key="server_dev",
        source_kind="server_api",
        active_server_url="http://mud.local:8000",
        username="admin",
        password="secret",
        base_url_override=None,
        default_base_url="http://127.0.0.1:8000",
        allowed_roles={"admin", "superuser"},
        normalize_base_url=lambda value: str(value or "").strip().rstrip("/"),
        fetch_mud_api_json_anonymous=lambda **_kwargs: {
            "session_id": "session-1",
            "role": "player",
        },
    )
    assert forbidden_payload.success is False
    assert forbidden_payload.session_id == "session-1"
    assert forbidden_payload.role == "player"


def test_build_policy_namespace_options_payload_passes_policy_type_filter() -> None:
    """Namespace options helper should include selected policy_type filter."""
    captured_query_params: dict[str, str] = {}

    def _fake_fetch(*, runtime, method, path, query_params):  # noqa: ANN001
        assert runtime.base_url == "http://mud.local:8000"
        assert method == "GET"
        assert path == "/api/policies"
        captured_query_params.update(query_params)
        return {
            "items": [
                {"namespace": "image.blocks.species"},
                {"namespace": "image.blocks.species"},
            ]
        }

    payload = web_runtime_services.build_policy_namespace_options_payload(
        source_kind="server_api",
        active_server_url="http://mud.local:8000",
        session_id_override="session-1",
        policy_type="species_block",
        base_url_override=None,
        resolve_runtime_config=lambda **_kwargs: MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id="session-1",
        ),
        fetch_mud_api_json=_fake_fetch,
    )
    assert captured_query_params == {"policy_type": "species_block"}
    assert payload.items == ["image.blocks.species"]
    assert payload.source == "mud_server_api"
