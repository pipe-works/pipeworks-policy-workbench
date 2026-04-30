"""Unit tests for FastAPI web endpoints in the policy workbench."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from policy_workbench import web_app as web_app_module
from policy_workbench import web_services
from policy_workbench.policy_authoring import PolicySaveResult, PolicyValidateResult
from policy_workbench.web_app import create_web_app
from policy_workbench.web_models import (
    PolicyActivationScopeResponse,
    PolicyActivationSetResponse,
    PolicyInventoryResponse,
    PolicyObjectDetailResponse,
    PolicyObjectSummaryResponse,
    PolicyPublishRunProxyResponse,
    PolicyTypeOptionsResponse,
    RuntimeAuthResponse,
    RuntimeLoginResponse,
)


def _write_text(path: Path, content: str) -> None:
    """Write UTF-8 content to ``path`` and create parents when needed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_client(tmp_path: Path) -> tuple[TestClient, Path, Path]:
    """Build a configured ``TestClient`` plus source/target fixture roots."""

    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir(parents=True)
    target_root.mkdir(parents=True)

    _write_text(source_root / "image" / "prompts" / "scene.txt", "new scene prompt")
    _write_text(source_root / "image" / "prompts" / "shared.txt", "same content")
    _write_text(
        source_root / "image" / "blocks" / "species" / "goblin_v1.yaml",
        "text: |\n  A canonical goblin prompt.\n",
    )

    _write_text(target_root / "image" / "prompts" / "scene.txt", "old scene prompt")
    _write_text(target_root / "image" / "prompts" / "shared.txt", "same content")
    _write_text(target_root / "image" / "prompts" / "extra.txt", "target only")

    app = create_web_app(source_root_override=str(source_root))
    return TestClient(app, base_url="https://testserver"), source_root, target_root


def _set_server_dev_mode(client: TestClient) -> None:
    """Switch runtime mode to server_dev for API-backed endpoint tests."""

    mode_response = client.post(
        "/api/runtime-mode",
        json={"mode_key": "server_dev", "server_url": "http://127.0.0.1:8000"},
    )
    assert mode_response.status_code == 200


def test_index_and_health_endpoints_return_expected_payloads(tmp_path: Path) -> None:
    """Root HTML and health endpoints should be available for runtime checks."""

    client, _, _ = _build_client(tmp_path)

    index_response = client.get("/")
    assert index_response.status_code == 200
    assert "Policy Workbench" in index_response.text

    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}


def test_runtime_mode_endpoints_switch_between_server_profiles(tmp_path: Path) -> None:
    """Runtime mode endpoints should expose and update server profile state."""
    client, _, _ = _build_client(tmp_path)

    initial_response = client.get("/api/runtime-mode")
    assert initial_response.status_code == 200
    initial_payload = initial_response.json()
    assert initial_payload["mode_key"] == "server_dev"
    assert initial_payload["source_kind"] == "server_api"
    assert initial_payload["active_server_url"] == "http://127.0.0.1:8000"
    assert {option["mode_key"] for option in initial_payload["options"]} == {
        "server_dev",
        "server_prod",
    }

    remote_response = client.post(
        "/api/runtime-mode",
        json={"mode_key": "server_dev", "server_url": "https://dev.example.test/"},
    )
    assert remote_response.status_code == 200
    remote_payload = remote_response.json()
    assert remote_payload["mode_key"] == "server_dev"
    assert remote_payload["source_kind"] == "server_api"
    assert remote_payload["active_server_url"] == "https://dev.example.test"

    invalid_response = client.post(
        "/api/runtime-mode",
        json={"mode_key": "not-a-mode"},
    )
    assert invalid_response.status_code == 400
    assert "Unknown runtime mode" in invalid_response.json()["detail"]

    invalid_url_response = client.post(
        "/api/runtime-mode",
        json={"mode_key": "server_dev", "server_url": "mud-dev.example.test"},
    )
    assert invalid_url_response.status_code == 400
    assert "absolute http(s)" in invalid_url_response.json()["detail"]


def test_runtime_auth_endpoint_returns_service_payload(tmp_path: Path, monkeypatch) -> None:
    """Runtime-auth endpoint should expose auth probe payload for current source mode."""

    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)
    captured: dict[str, object] = {}

    def _fake_runtime_auth_builder(**kwargs):
        captured.update(kwargs)
        return RuntimeAuthResponse(
            mode_key="server_dev",
            source_kind="server_api",
            active_server_url="http://127.0.0.1:8000",
            session_present=True,
            access_granted=True,
            status="authorized",
            detail="Session is authorized for admin/superuser policy APIs.",
        )

    monkeypatch.setattr(web_app_module, "build_runtime_auth_payload", _fake_runtime_auth_builder)

    response = client.get("/api/runtime-auth")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "authorized"
    assert payload["access_granted"] is True
    assert captured == {
        "mode_key": "server_dev",
        "source_kind": "server_api",
        "active_server_url": "http://127.0.0.1:8000",
        "session_id_override": None,
        "base_url_override": "http://127.0.0.1:8000",
    }


def test_runtime_login_endpoint_returns_service_payload(tmp_path: Path, monkeypatch) -> None:
    """Runtime-login endpoint should set secure cookie and hide raw session IDs."""

    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)
    captured: dict[str, object] = {}

    def _fake_runtime_login_builder(**kwargs):
        captured.update(kwargs)
        return RuntimeLoginResponse(
            success=True,
            session_id="session-admin-1",
            role="admin",
            detail="Authenticated as admin/superuser.",
        )

    monkeypatch.setattr(web_app_module, "build_runtime_login_payload", _fake_runtime_login_builder)

    response = client.post(
        "/api/runtime-login",
        json={"username": "admin-user", "password": "secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["session_id"] is None
    assert payload["role"] == "admin"
    assert payload["available_worlds"] == []
    assert "HttpOnly" in response.headers.get("set-cookie", "")
    assert captured == {
        "mode_key": "server_dev",
        "source_kind": "server_api",
        "active_server_url": "http://127.0.0.1:8000",
        "username": "admin-user",
        "password": "secret",
        "base_url_override": "http://127.0.0.1:8000",
    }


def test_runtime_auth_endpoint_uses_cookie_session_from_runtime_login(
    tmp_path: Path, monkeypatch
) -> None:
    """Runtime-auth should resolve session from secure browser cookie when query is empty."""

    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)

    monkeypatch.setattr(
        web_app_module,
        "build_runtime_login_payload",
        lambda **_kwargs: RuntimeLoginResponse(
            success=True,
            session_id="cookie-session-1",
            role="admin",
            available_worlds=[{"id": "pipeworks_web", "name": "Pipeworks Web"}],
            detail="Authenticated as admin/superuser.",
        ),
    )
    login_response = client.post(
        "/api/runtime-login",
        json={"username": "admin-user", "password": "secret"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["session_id"] is None

    captured: dict[str, object] = {}

    def _fake_runtime_auth_builder(**kwargs):
        captured.update(kwargs)
        return RuntimeAuthResponse(
            mode_key="server_dev",
            source_kind="server_api",
            active_server_url="http://127.0.0.1:8000",
            session_present=True,
            access_granted=True,
            status="authorized",
            detail="Session is authorized for admin/superuser policy APIs.",
        )

    monkeypatch.setattr(web_app_module, "build_runtime_auth_payload", _fake_runtime_auth_builder)
    auth_response = client.get("/api/runtime-auth")

    assert auth_response.status_code == 200
    auth_payload = auth_response.json()
    assert auth_payload["status"] == "authorized"
    assert auth_payload["available_worlds"] == [{"id": "pipeworks_web", "name": "Pipeworks Web"}]
    assert captured["session_id_override"] == "cookie-session-1"


def test_runtime_logout_clears_cookie_backed_session(tmp_path: Path, monkeypatch) -> None:
    """Runtime-logout should remove browser session cookie and server token binding."""

    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)
    monkeypatch.setattr(
        web_app_module,
        "build_runtime_login_payload",
        lambda **_kwargs: RuntimeLoginResponse(
            success=True,
            session_id="cookie-session-2",
            role="admin",
            available_worlds=[],
            detail="Authenticated as admin/superuser.",
        ),
    )
    login_response = client.post(
        "/api/runtime-login",
        json={"username": "admin-user", "password": "secret"},
    )
    assert login_response.status_code == 200

    logout_response = client.post("/api/runtime-logout")
    assert logout_response.status_code == 200
    assert logout_response.json()["success"] is True

    captured: dict[str, object] = {}

    def _fake_runtime_auth_builder(**kwargs):
        captured.update(kwargs)
        return RuntimeAuthResponse(
            mode_key="server_dev",
            source_kind="server_api",
            active_server_url="http://127.0.0.1:8000",
            session_present=False,
            access_granted=False,
            status="missing_session",
            detail="No active runtime session. Login with an admin/superuser account.",
        )

    monkeypatch.setattr(web_app_module, "build_runtime_auth_payload", _fake_runtime_auth_builder)
    auth_response = client.get("/api/runtime-auth")
    assert auth_response.status_code == 200
    assert captured["session_id_override"] is None


def test_runtime_login_endpoint_maps_mode_error_to_400(tmp_path: Path, monkeypatch) -> None:
    """Runtime-login endpoint should map mode/config errors to HTTP 400."""

    client, _, _ = _build_client(tmp_path)
    monkeypatch.setattr(
        web_app_module,
        "build_runtime_login_payload",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("Runtime mode must be server_api.")),
    )

    response = client.post(
        "/api/runtime-login",
        json={"username": "admin-user", "password": "secret"},
    )
    assert response.status_code == 400
    assert "Runtime mode must be server_api." in response.json()["detail"]


def test_policy_types_endpoint_returns_service_payload(tmp_path: Path, monkeypatch) -> None:
    """Policy-types endpoint should proxy canonical options helper payload."""

    client, _, _ = _build_client(tmp_path)
    captured: dict[str, object] = {}

    def _fake_policy_types_builder(**kwargs):
        captured.update(kwargs)
        return PolicyTypeOptionsResponse(
            items=["species_block", "registry", "prompt"],
            source="mud_server_api",
            detail="Policy types resolved from mud-server policy capabilities.",
        )

    monkeypatch.setattr(
        web_app_module,
        "build_policy_type_options_payload",
        _fake_policy_types_builder,
    )

    response = client.get("/api/policy-types", params={"session_id": "s1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == ["species_block", "registry", "prompt"]
    assert payload["source"] == "mud_server_api"
    assert captured == {
        "source_kind": "server_api",
        "active_server_url": "http://127.0.0.1:8000",
        "session_id_override": "s1",
        "base_url_override": "http://127.0.0.1:8000",
    }


def test_policy_namespaces_endpoint_returns_service_payload(tmp_path: Path, monkeypatch) -> None:
    """Policy-namespaces endpoint should proxy namespace option helper payload."""

    client, _, _ = _build_client(tmp_path)
    captured: dict[str, object] = {}

    def _fake_policy_namespaces_builder(**kwargs):
        captured.update(kwargs)
        return PolicyTypeOptionsResponse(
            items=["image.blocks.species", "image.registries"],
            source="mud_server_api",
            detail="Namespaces resolved from mud-server API inventory.",
        )

    monkeypatch.setattr(
        web_app_module,
        "build_policy_namespace_options_payload",
        _fake_policy_namespaces_builder,
    )

    response = client.get(
        "/api/policy-namespaces",
        params={"policy_type": "species_block", "session_id": "s1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == ["image.blocks.species", "image.registries"]
    assert captured["source_kind"] == "server_api"
    assert captured["active_server_url"] == "http://127.0.0.1:8000"
    assert captured["session_id_override"] == "s1"
    assert captured["policy_type"] == "species_block"
    assert captured["base_url_override"] == "http://127.0.0.1:8000"


def test_policy_statuses_endpoint_returns_service_payload(tmp_path: Path, monkeypatch) -> None:
    """Policy-statuses endpoint should proxy canonical status helper payload."""

    client, _, _ = _build_client(tmp_path)
    captured: dict[str, object] = {}

    def _fake_policy_statuses_builder(**kwargs):
        captured.update(kwargs)
        return PolicyTypeOptionsResponse(
            items=["draft", "candidate", "active", "archived"],
            source="mud_server_api",
            detail="Statuses resolved from mud-server policy capabilities.",
        )

    monkeypatch.setattr(
        web_app_module,
        "build_policy_status_options_payload",
        _fake_policy_statuses_builder,
    )

    response = client.get("/api/policy-statuses", params={"session_id": "s1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == ["draft", "candidate", "active", "archived"]
    assert captured == {
        "source_kind": "server_api",
        "active_server_url": "http://127.0.0.1:8000",
        "session_id_override": "s1",
        "base_url_override": "http://127.0.0.1:8000",
    }


def test_policy_types_endpoint_maps_auth_error_to_403(tmp_path: Path, monkeypatch) -> None:
    """Policy-types endpoint should map role-denied builder failures to HTTP 403."""

    client, _, _ = _build_client(tmp_path)
    monkeypatch.setattr(
        web_app_module,
        "build_policy_type_options_payload",
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("forbidden: Policy API requires admin or superuser role.")
        ),
    )
    response = client.get("/api/policy-types", params={"session_id": "s1"})
    assert response.status_code == 403
    assert "admin or superuser role" in response.json()["detail"]


def test_policy_statuses_endpoint_maps_missing_session_to_400(tmp_path: Path, monkeypatch) -> None:
    """Policy-statuses endpoint should map runtime/session config failures to HTTP 400."""

    client, _, _ = _build_client(tmp_path)
    monkeypatch.setattr(
        web_app_module,
        "build_policy_status_options_payload",
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("Mud API session id is required (PW_POLICY_MUD_SESSION_ID).")
        ),
    )
    response = client.get("/api/policy-statuses")
    assert response.status_code == 400
    assert "session id is required" in response.json()["detail"]


def test_legacy_tree_and_file_endpoints_are_disabled(tmp_path: Path) -> None:
    """Legacy tree/file APIs should fail closed with explicit 410 responses."""

    client, _, _ = _build_client(tmp_path)

    tree_response = client.get("/api/tree")
    assert tree_response.status_code == 410
    assert "Legacy tree endpoint is disabled" in tree_response.json()["detail"]

    read_response = client.get("/api/file", params={"relative_path": "image/prompts/scene.txt"})
    assert read_response.status_code == 410
    assert "Legacy file endpoint is disabled" in read_response.json()["detail"]

    write_response = client.put(
        "/api/file",
        json={"relative_path": "image/prompts/scene.txt", "content": "edited prompt text"},
    )
    assert write_response.status_code == 410
    assert "Legacy file endpoint is disabled" in write_response.json()["detail"]


def test_legacy_source_override_query_params_are_rejected(tmp_path: Path) -> None:
    """Legacy ``root`` and ``map_path`` query overrides should fail closed."""

    client, _, _ = _build_client(tmp_path)

    tree_response = client.get("/api/tree", params={"root": "/tmp/override"})
    assert tree_response.status_code == 410
    assert "Legacy tree endpoint is disabled" in tree_response.json()["detail"]

    file_response = client.get(
        "/api/file",
        params={
            "relative_path": "image/prompts/scene.txt",
            "map_path": "/tmp/map.yaml",
        },
    )
    assert file_response.status_code == 410
    assert "Legacy file endpoint is disabled" in file_response.json()["detail"]

    write_response = client.put(
        "/api/file",
        params={"root": "/tmp/override"},
        json={"relative_path": "image/prompts/scene.txt", "content": "edited prompt text"},
    )
    assert write_response.status_code == 410
    assert "Legacy file endpoint is disabled" in write_response.json()["detail"]


def test_api_first_inventory_and_detail_endpoints_proxy_service_payloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """API-first inventory/detail endpoints should proxy mud-server payload models."""
    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)

    captured_inventory_kwargs: dict[str, object] = {}
    captured_detail_kwargs: dict[str, object] = {}

    def _fake_inventory_builder(**kwargs):
        captured_inventory_kwargs.update(kwargs)
        return PolicyInventoryResponse(
            filters={"policy_type": "species_block", "namespace": None, "status": "draft"},
            item_count=1,
            items=[
                PolicyObjectSummaryResponse(
                    policy_id="species_block:image.blocks.species:goblin",
                    policy_type="species_block",
                    namespace="image.blocks.species",
                    policy_key="goblin",
                    variant="v1",
                    schema_version="1.0",
                    policy_version=1,
                    status="draft",
                    content_hash="hash-goblin",
                    updated_at="2026-03-11T20:00:00Z",
                    updated_by="tester",
                )
            ],
        )

    def _fake_detail_builder(**kwargs):
        captured_detail_kwargs.update(kwargs)
        return PolicyObjectDetailResponse(
            policy_id="species_block:image.blocks.species:goblin",
            policy_type="species_block",
            namespace="image.blocks.species",
            policy_key="goblin",
            variant="v1",
            schema_version="1.0",
            policy_version=1,
            status="draft",
            content={"text": "Goblin text"},
            content_hash="hash-goblin",
            updated_at="2026-03-11T20:00:00Z",
            updated_by="tester",
        )

    monkeypatch.setattr(web_app_module, "build_policy_inventory_payload", _fake_inventory_builder)
    monkeypatch.setattr(web_app_module, "build_policy_object_detail_payload", _fake_detail_builder)

    inventory_response = client.get(
        "/api/policies",
        params={"policy_type": "species_block", "status": "draft", "session_id": "s1"},
    )
    assert inventory_response.status_code == 200
    inventory_payload = inventory_response.json()
    assert inventory_payload["item_count"] == 1
    assert inventory_payload["items"][0]["policy_id"] == "species_block:image.blocks.species:goblin"
    assert captured_inventory_kwargs == {
        "policy_type": "species_block",
        "namespace": None,
        "status": "draft",
        "session_id_override": "s1",
        "base_url_override": "http://127.0.0.1:8000",
    }

    detail_response = client.get(
        "/api/policies/species_block:image.blocks.species:goblin",
        params={"variant": "v1", "session_id": "s1"},
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["content"]["text"] == "Goblin text"
    assert captured_detail_kwargs == {
        "policy_id": "species_block:image.blocks.species:goblin",
        "variant": "v1",
        "session_id_override": "s1",
        "base_url_override": "http://127.0.0.1:8000",
    }


def test_api_first_activation_and_publish_proxy_endpoints(tmp_path: Path, monkeypatch) -> None:
    """Activation/publish proxy endpoints should return normalized service payloads."""
    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)

    monkeypatch.setattr(
        web_app_module,
        "build_policy_activation_scope_payload",
        lambda **_kwargs: PolicyActivationScopeResponse(
            world_id="pipeworks_web",
            client_profile="mobile",
            items=[
                {
                    "world_id": "pipeworks_web",
                    "client_profile": "mobile",
                    "policy_id": "species_block:image.blocks.species:goblin",
                    "variant": "v1",
                }
            ],
        ),
    )
    monkeypatch.setattr(
        web_app_module,
        "build_policy_publish_run_payload",
        lambda **_kwargs: PolicyPublishRunProxyResponse(
            publish_run_id=7,
            world_id="pipeworks_web",
            client_profile="mobile",
            actor="tester",
            created_at="2026-03-11T20:00:00Z",
            manifest={"manifest_hash": "abc"},
            artifact={"artifact_hash": "def", "artifact_path": "/tmp/export.json"},
        ),
    )
    monkeypatch.setattr(
        web_app_module,
        "build_policy_activation_set_payload",
        lambda **_kwargs: PolicyActivationSetResponse(
            world_id="pipeworks_web",
            client_profile="mobile",
            policy_id="descriptor_layer:image.descriptors:id_card",
            variant="v1-w-pipeworks-web-cp-mobile",
            activated_at="2026-03-15T12:00:00Z",
            activated_by="tester",
            rollback_of_activation_id=None,
            audit_event_id=401,
        ),
    )

    activation_response = client.get(
        "/api/policy-activations-live",
        params={"scope": "pipeworks_web:mobile", "effective": "false", "session_id": "s1"},
    )
    assert activation_response.status_code == 200
    activation_payload = activation_response.json()
    assert activation_payload["world_id"] == "pipeworks_web"
    assert activation_payload["items"][0]["variant"] == "v1"

    activation_set_response = client.post(
        "/api/policy-activation-set",
        json={
            "world_id": "pipeworks_web",
            "client_profile": "mobile",
            "policy_id": "descriptor_layer:image.descriptors:id_card",
            "variant": "v1-w-pipeworks-web-cp-mobile",
            "session_id": "s1",
        },
    )
    assert activation_set_response.status_code == 200
    activation_set_payload = activation_set_response.json()
    assert activation_set_payload["world_id"] == "pipeworks_web"
    assert activation_set_payload["audit_event_id"] == 401

    publish_response = client.get(
        "/api/policy-publish-runs/7",
        params={"session_id": "s1"},
    )
    assert publish_response.status_code == 200
    publish_payload = publish_response.json()
    assert publish_payload["publish_run_id"] == 7
    assert publish_payload["artifact"]["artifact_hash"] == "def"


def test_api_first_activation_endpoint_rejects_whitespace_scope(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Activation endpoint should map blank-after-trim scopes to HTTP 400."""

    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)

    def _fake_activation_builder(**kwargs):
        if not str(kwargs["scope"]).strip():
            raise ValueError("scope is required.")
        raise AssertionError("Expected whitespace scope branch")  # pragma: no cover

    monkeypatch.setattr(
        web_app_module,
        "build_policy_activation_scope_payload",
        _fake_activation_builder,
    )

    response = client.get(
        "/api/policy-activations-live",
        params={"scope": "   ", "effective": "true", "session_id": "s1"},
    )
    assert response.status_code == 400
    assert "scope is required." in response.json()["detail"]


def test_api_first_proxy_endpoints_map_service_errors_to_http_400(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """API-first proxy endpoints should map service ValueError failures to HTTP 400."""
    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)

    monkeypatch.setattr(
        web_app_module,
        "build_policy_inventory_payload",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("inventory failure")),
    )
    inventory_response = client.get("/api/policies")
    assert inventory_response.status_code == 400
    assert "inventory failure" in inventory_response.json()["detail"]

    monkeypatch.setattr(
        web_app_module,
        "build_policy_object_detail_payload",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("detail failure")),
    )
    detail_response = client.get("/api/policies/species_block:image.blocks.species:goblin")
    assert detail_response.status_code == 400
    assert "detail failure" in detail_response.json()["detail"]

    monkeypatch.setattr(
        web_app_module,
        "build_policy_activation_scope_payload",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("activation failure")),
    )
    activation_response = client.get(
        "/api/policy-activations-live",
        params={"scope": "pipeworks_web"},
    )
    assert activation_response.status_code == 400
    assert "activation failure" in activation_response.json()["detail"]

    monkeypatch.setattr(
        web_app_module,
        "build_policy_activation_set_payload",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("activation set failure")),
    )
    activation_set_response = client.post(
        "/api/policy-activation-set",
        json={
            "world_id": "pipeworks_web",
            "policy_id": "descriptor_layer:image.descriptors:id_card",
            "variant": "v1",
        },
    )
    assert activation_set_response.status_code == 400
    assert "activation set failure" in activation_set_response.json()["detail"]

    monkeypatch.setattr(
        web_app_module,
        "build_policy_publish_run_payload",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("publish failure")),
    )
    publish_response = client.get("/api/policy-publish-runs/1")
    assert publish_response.status_code == 400
    assert "publish failure" in publish_response.json()["detail"]


def test_api_first_proxy_endpoints_map_auth_failures_to_401_and_403(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Proxy endpoints should preserve mud-server auth semantics (401/403)."""
    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)

    monkeypatch.setattr(
        web_app_module,
        "build_policy_inventory_payload",
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("Mud API request failed: Policy API requires admin or superuser role.")
        ),
    )
    forbidden_response = client.get("/api/policies")
    assert forbidden_response.status_code == 403
    assert "admin or superuser" in forbidden_response.json()["detail"]

    monkeypatch.setattr(
        web_app_module,
        "build_policy_inventory_payload",
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("Mud API request failed: Invalid or expired session")
        ),
    )
    unauthenticated_response = client.get("/api/policies")
    assert unauthenticated_response.status_code == 401
    assert "Invalid or expired session" in unauthenticated_response.json()["detail"]


def test_proxy_401_clears_runtime_session_cookie_and_drops_record(
    tmp_path: Path, monkeypatch
) -> None:
    """A mud-server 'Invalid or expired session' must drop the cached browser session.

    Otherwise the workbench keeps forwarding the same dead session_id on every
    click and the auth badge stays stuck on a stale 'authorized' reading.
    """

    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)

    monkeypatch.setattr(
        web_app_module,
        "build_runtime_login_payload",
        lambda **_kwargs: RuntimeLoginResponse(
            success=True,
            session_id="cached-session-xyz",
            role="admin",
            available_worlds=[],
            detail="Authenticated as admin/superuser.",
        ),
    )
    login_response = client.post(
        "/api/runtime-login",
        json={"username": "admin-user", "password": "secret"},
    )
    assert login_response.status_code == 200
    assert client.cookies.get("pw_policy_runtime_session")

    monkeypatch.setattr(
        web_app_module,
        "build_policy_object_detail_payload",
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("Mud API request failed: Invalid or expired session")
        ),
    )

    detail_response = client.get("/api/policies/clothing_block:image.blocks.x:y")
    assert detail_response.status_code == 401
    set_cookie_header = detail_response.headers.get("set-cookie", "")
    assert "pw_policy_runtime_session=" in set_cookie_header
    assert "Max-Age=0" in set_cookie_header or "expires=" in set_cookie_header.lower()
    assert client.cookies.get("pw_policy_runtime_session") in (None, "")


def test_api_first_proxy_endpoints_return_503_when_runtime_mode_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Mud-server backed proxy endpoints should fail closed when runtime mode is unavailable."""
    client, _, _ = _build_client(tmp_path)
    monkeypatch.setattr(
        web_app_module,
        "require_server_api_url",
        lambda: (_ for _ in ()).throw(
            web_app_module.RuntimeModeUnavailableError("runtime mode unavailable")
        ),
    )

    inventory_response = client.get("/api/policies")
    assert inventory_response.status_code == 503
    assert "runtime mode unavailable" in inventory_response.json()["detail"]

    activation_response = client.get(
        "/api/policy-activations-live",
        params={"scope": "pipeworks_web"},
    )
    assert activation_response.status_code == 503
    assert "runtime mode unavailable" in activation_response.json()["detail"]

    activation_set_response = client.post(
        "/api/policy-activation-set",
        json={
            "world_id": "pipeworks_web",
            "policy_id": "descriptor_layer:image.descriptors:id_card",
            "variant": "v1",
        },
    )
    assert activation_set_response.status_code == 503
    assert "runtime mode unavailable" in activation_set_response.json()["detail"]

    publish_response = client.get("/api/policy-publish-runs/1")
    assert publish_response.status_code == 503
    assert "runtime mode unavailable" in publish_response.json()["detail"]


def test_policy_save_endpoint_runs_phase2_api_only_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Policy-save endpoint should call mud-server flow and return normalized payload."""
    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)

    monkeypatch.setattr(
        web_app_module,
        "resolve_runtime_config",
        lambda session_id_override=None, base_url_override=None: object(),
    )
    monkeypatch.setattr(
        web_app_module,
        "save_policy_variant_from_raw_content",
        lambda **kwargs: PolicySaveResult(
            policy_id="species_block:image.blocks.species:goblin",
            variant="v1",
            policy_version=3,
            content_hash="hash-123",
            validation_run_id=55,
            activation_audit_event_id=901,
        ),
    )

    response = client.post(
        "/api/policy-save",
        json={
            "policy_type": "species_block",
            "namespace": "image.blocks.species",
            "policy_key": "goblin",
            "variant": "v1",
            "raw_content": "text: |\n  Goblin body text.\n",
            "schema_version": "1.0",
            "status": "candidate",
            "activate": True,
            "world_id": "pipeworks_web",
            "actor": "tester",
            "session_id": "s1",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["policy_id"] == "species_block:image.blocks.species:goblin"
    assert payload["variant"] == "v1"
    assert payload["policy_version"] == 3
    assert payload["validation_run_id"] == 55
    assert payload["activated"] is True
    assert payload["activation_audit_event_id"] == 901


def test_policy_validate_endpoint_runs_phase2_validate_only_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Policy-validate endpoint should call validate-only flow and return normalized payload."""
    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)

    monkeypatch.setattr(
        web_app_module,
        "resolve_runtime_config",
        lambda session_id_override=None, base_url_override=None: object(),
    )
    monkeypatch.setattr(
        web_app_module,
        "validate_policy_variant_from_raw_content",
        lambda **kwargs: PolicyValidateResult(
            policy_id="species_block:image.blocks.species:goblin",
            variant="v1",
            policy_version=4,
            validation_run_id=77,
        ),
    )

    response = client.post(
        "/api/policy-validate",
        json={
            "policy_type": "species_block",
            "namespace": "image.blocks.species",
            "policy_key": "goblin",
            "variant": "v1",
            "raw_content": '{"text":"Goblin body text."}',
            "schema_version": "1.0",
            "status": "draft",
            "actor": "tester",
            "session_id": "s1",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["policy_id"] == "species_block:image.blocks.species:goblin"
    assert payload["variant"] == "v1"
    assert payload["policy_version"] == 4
    assert payload["validation_run_id"] == 77
    assert payload["is_valid"] is True


def test_policy_save_endpoint_returns_400_when_runtime_config_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Policy-save endpoint should map runtime/config errors to HTTP 400."""
    client, _, _ = _build_client(tmp_path)
    _set_server_dev_mode(client)
    monkeypatch.setattr(
        web_app_module,
        "resolve_runtime_config",
        lambda session_id_override=None, base_url_override=None: (_ for _ in ()).throw(
            ValueError("missing session id")
        ),
    )

    response = client.post(
        "/api/policy-save",
        json={
            "policy_type": "species_block",
            "namespace": "image.blocks.species",
            "policy_key": "goblin",
            "variant": "v1",
            "raw_content": "text: |\n  Goblin body text.\n",
        },
    )
    assert response.status_code == 400
    assert "missing session id" in response.json()["detail"]


def test_policy_save_endpoint_returns_503_when_runtime_mode_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Policy save should fail closed when runtime mode is unavailable."""
    client, _, _ = _build_client(tmp_path)
    monkeypatch.setattr(
        web_app_module,
        "require_server_api_url",
        lambda: (_ for _ in ()).throw(
            web_app_module.RuntimeModeUnavailableError("runtime mode unavailable")
        ),
    )

    response = client.post(
        "/api/policy-save",
        json={
            "policy_type": "species_block",
            "namespace": "image.blocks.species",
            "policy_key": "goblin",
            "variant": "v1",
            "raw_content": "text: |\n  Goblin body text.\n",
        },
    )
    assert response.status_code == 503
    assert "runtime mode unavailable" in response.json()["detail"]


def test_sync_impact_endpoints_are_removed_from_web_app(tmp_path: Path) -> None:
    """Sync/Hash routes should be absent after Sync Impact removal from the web UI."""

    client, _, _ = _build_client(tmp_path)
    assert client.get("/api/hash-status").status_code == 404
    assert client.get("/api/validate").status_code == 404
    assert client.get("/api/sync-plan").status_code == 404
    sync_compare_response = client.get(
        "/api/sync-compare",
        params={"relative_path": "image/prompts/scene.txt"},
    )
    assert sync_compare_response.status_code == 404
    assert client.post("/api/sync-apply", json={"confirm": True}).status_code == 404


def test_resolve_canonical_hash_snapshot_url_precedence_and_empty_guard(
    monkeypatch,
) -> None:
    """Canonical URL resolver should honor override/env/default precedence."""

    monkeypatch.delenv("PW_POLICY_HASH_SNAPSHOT_URL", raising=False)
    assert web_services._resolve_canonical_hash_snapshot_url("http://override.local/api") == (
        "http://override.local/api"
    )

    monkeypatch.setenv("PW_POLICY_HASH_SNAPSHOT_URL", "http://env.local/api")
    assert web_services._resolve_canonical_hash_snapshot_url(None) == "http://env.local/api"

    monkeypatch.delenv("PW_POLICY_HASH_SNAPSHOT_URL", raising=False)
    assert web_services._resolve_canonical_hash_snapshot_url(None) == (
        "http://127.0.0.1:8000/api/policy/hash-snapshot"
    )

    monkeypatch.setattr(web_services, "_DEFAULT_CANONICAL_HASH_URL", "")
    with pytest.raises(ValueError, match="must not be empty"):
        web_services._resolve_canonical_hash_snapshot_url("   ")


def test_fetch_canonical_hash_snapshot_handles_success_and_error_paths(monkeypatch) -> None:
    """Canonical snapshot fetch helper should validate both payload and transport errors."""

    class _FakeHttpResponse:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._payload

    valid_payload = {
        "hash_version": "policy_tree_hash_v1",
        "canonical_root": "/tmp/source",
        "generated_at": "2026-03-10T12:00:00Z",
        "file_count": 1,
        "root_hash": "abc123",
        "directories": [],
    }
    monkeypatch.setattr(
        web_services,
        "urlopen",
        lambda _request, timeout=5.0: _FakeHttpResponse(json.dumps(valid_payload).encode("utf-8")),
    )
    snapshot = web_services._fetch_canonical_hash_snapshot("http://canonical.local/api")
    assert snapshot.root_hash == "abc123"

    monkeypatch.setattr(
        web_services,
        "urlopen",
        lambda _request, timeout=5.0: (_ for _ in ()).throw(URLError("unreachable")),
    )
    with pytest.raises(ValueError, match="Unable to fetch canonical hash snapshot"):
        web_services._fetch_canonical_hash_snapshot("http://canonical.local/api")

    monkeypatch.setattr(
        web_services,
        "urlopen",
        lambda _request, timeout=5.0: _FakeHttpResponse(json.dumps(valid_payload).encode("utf-8")),
    )
    monkeypatch.setattr(
        web_services.HashCanonicalResponse,
        "model_validate",
        staticmethod(lambda _payload: {}),
    )
    with pytest.raises(ValueError, match="did not match expected schema"):
        web_services._fetch_canonical_hash_snapshot("http://canonical.local/api")


def test_service_hash_helpers_cover_path_guards_and_io_edges(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Service hash helper utilities should enforce path/IO guardrails."""

    assert web_services._normalize_relative_path(r"image\prompts\scene.txt") == (
        "image/prompts/scene.txt"
    )
    with pytest.raises(ValueError, match="must not be empty"):
        web_services._normalize_relative_path("")
    with pytest.raises(ValueError, match="must not traverse upwards"):
        web_services._normalize_relative_path("../scene.txt")

    assert web_services._read_optional_text(None) is None
    assert web_services._read_optional_text(tmp_path / "missing.txt") is None

    directory_path = tmp_path / "directory"
    directory_path.mkdir(parents=True, exist_ok=True)
    assert web_services._read_optional_text(directory_path) is None

    existing_file = tmp_path / "broken.txt"
    existing_file.write_text("content", encoding="utf-8")
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, encoding="utf-8": (_ for _ in ()).throw(OSError("boom")),
    )
    with pytest.raises(ValueError, match="Unable to read text for diff"):
        web_services._read_optional_text(existing_file)


def test_service_hash_helpers_use_ipc_helper_branches(monkeypatch) -> None:
    """Hash helper methods should use IPC implementations when available."""

    class _FakePolicyHashEntry:
        def __init__(self, *, relative_path: str, content_hash: str) -> None:
            self.relative_path = relative_path
            self.content_hash = content_hash

    fake_hashing = SimpleNamespace(
        PolicyHashEntry=_FakePolicyHashEntry,
        compute_policy_file_hash=lambda relative_path, _bytes: f"file::{relative_path}",
        compute_policy_tree_hash=lambda entries: f"tree::{len(entries)}",
    )
    monkeypatch.setattr(web_services, "ipc_hashing", fake_hashing)

    assert web_services._compute_file_hash("image/prompts/scene.txt", b"content") == (
        "file::image/prompts/scene.txt"
    )

    entries = [
        web_services._PolicyHashEntry(relative_path="image/prompts/scene.txt", content_hash="h1"),
        web_services._PolicyHashEntry(relative_path="image/prompts/other.txt", content_hash="h2"),
    ]
    assert web_services._compute_tree_hash(entries) == "tree::2"
