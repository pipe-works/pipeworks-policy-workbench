"""Unit tests for targeted web-service helper edge cases."""

from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

from policy_workbench import web_services


def test_read_optional_text_returns_none_for_none_and_missing_file(tmp_path: Path) -> None:
    """Optional reads should return ``None`` when no readable text file exists."""

    assert web_services._read_optional_text(None) is None
    assert web_services._read_optional_text(tmp_path / "missing.txt") is None


def test_read_optional_text_wraps_decode_errors_as_value_error(tmp_path: Path) -> None:
    """Unreadable bytes should surface as a stable ``ValueError`` contract."""

    binary_path = tmp_path / "invalid.txt"
    binary_path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(ValueError, match="Unable to read text for diff"):
        web_services._read_optional_text(binary_path)


def test_content_signature_and_canonical_label_cover_special_cases() -> None:
    """Signature/label helpers should handle missing/unreadable files and mud-server roots."""

    assert web_services._content_signature(source_content="ignored", exists=False) == "__missing__"
    assert web_services._content_signature(source_content=None, exists=True) == "__unreadable__"

    expected_hash = web_services.compute_payload_hash({"content": "canonical text"})
    assert web_services._content_signature(source_content="canonical text", exists=True) == str(
        expected_hash
    )

    mud_server_root = Path("/tmp/pipeworks_mud_server/data/worlds/pipeworks_web/policies")
    assert web_services._canonical_source_label(mud_server_root) == "canonical-source: mud-server"


def test_resolve_mud_api_runtime_config_uses_env_and_override(monkeypatch) -> None:
    """Mud API runtime config should normalize URL and prefer explicit session override."""

    monkeypatch.setenv("PW_POLICY_MUD_API_BASE_URL", " http://mud.local:8123/ ")
    monkeypatch.setenv("PW_POLICY_MUD_SESSION_ID", "session-from-env")

    runtime = web_services._resolve_mud_api_runtime_config(session_id_override=None)
    assert runtime.base_url == "http://mud.local:8123"
    assert runtime.session_id == "session-from-env"

    override_runtime = web_services._resolve_mud_api_runtime_config(
        session_id_override="session-override"
    )
    assert override_runtime.session_id == "session-override"


def test_resolve_mud_api_runtime_config_rejects_missing_base_url_and_session(monkeypatch) -> None:
    """Runtime config resolver should fail fast when required inputs are missing."""

    monkeypatch.setenv("PW_POLICY_MUD_API_BASE_URL", "   ")
    monkeypatch.setenv("PW_POLICY_MUD_SESSION_ID", "session-from-env")
    with pytest.raises(ValueError, match="base URL must not be empty"):
        web_services._resolve_mud_api_runtime_config(session_id_override=None)

    monkeypatch.setenv("PW_POLICY_MUD_API_BASE_URL", "http://mud.local:8000")
    monkeypatch.delenv("PW_POLICY_MUD_SESSION_ID", raising=False)
    with pytest.raises(ValueError, match="session id is required"):
        web_services._resolve_mud_api_runtime_config(session_id_override=None)


def test_fetch_mud_api_json_builds_url_and_returns_object_payload(monkeypatch) -> None:
    """Transport helper should append session_id and parse object JSON responses."""

    class _FakeHttpResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def __enter__(self) -> _FakeHttpResponse:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    captured: dict[str, str] = {}

    def _fake_urlopen(request, timeout=8.0):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["timeout"] = str(timeout)
        return _FakeHttpResponse({"items": []})

    monkeypatch.setattr(web_services, "urlopen", _fake_urlopen)

    runtime = web_services._MudApiRuntimeConfig(base_url="http://mud.local:8000", session_id="s1")
    payload = web_services._fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path="/api/policies",
        query_params={"policy_type": "species_block", "status": "draft", "empty": ""},
    )

    assert payload == {"items": []}
    assert captured["method"] == "GET"
    assert captured["timeout"] == "8.0"
    parsed = urlparse(captured["url"])
    assert parsed.path == "/api/policies"
    assert parse_qs(parsed.query) == {
        "policy_type": ["species_block"],
        "status": ["draft"],
        "session_id": ["s1"],
    }


def test_fetch_mud_api_json_maps_http_transport_and_schema_errors(monkeypatch) -> None:
    """Transport helper should raise stable ValueError messages across failure modes."""

    runtime = web_services._MudApiRuntimeConfig(base_url="http://mud.local:8000", session_id="s1")

    http_error = HTTPError(
        url="http://mud.local:8000/api/policies",
        code=403,
        msg="Forbidden",
        hdrs=None,
        fp=io.BytesIO(b'{"code":"forbidden","detail":"denied"}'),
    )
    monkeypatch.setattr(
        web_services, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(http_error)
    )
    with pytest.raises(ValueError, match="forbidden: denied"):
        web_services._fetch_mud_api_json(
            runtime=runtime,
            method="GET",
            path="/api/policies",
            query_params={},
        )

    monkeypatch.setattr(
        web_services,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("connection refused")),
    )
    with pytest.raises(ValueError, match="connection refused"):
        web_services._fetch_mud_api_json(
            runtime=runtime,
            method="GET",
            path="/api/policies",
            query_params={},
        )

    class _ArrayHttpResponse:
        def __enter__(self) -> _ArrayHttpResponse:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return b'["invalid"]'

    monkeypatch.setattr(web_services, "urlopen", lambda *_args, **_kwargs: _ArrayHttpResponse())
    with pytest.raises(ValueError, match="must be a JSON object"):
        web_services._fetch_mud_api_json(
            runtime=runtime,
            method="GET",
            path="/api/policies",
            query_params={},
        )


def test_build_policy_inventory_payload_filters_and_serializes_items(monkeypatch) -> None:
    """Inventory builder should normalize filters and return summary rows."""

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id=(session_id_override or "s1"),
        ),
    )

    def _fake_fetch(*, runtime, method, path, query_params):  # noqa: ANN001
        captured["runtime"] = runtime
        captured["method"] = method
        captured["path"] = path
        captured["query_params"] = query_params
        return {
            "items": [
                {
                    "policy_id": "species_block:image.blocks.species:goblin",
                    "policy_type": "species_block",
                    "namespace": "image.blocks.species",
                    "policy_key": "goblin",
                    "variant": "v1",
                    "schema_version": "1.0",
                    "policy_version": 4,
                    "status": "draft",
                    "content": {"text": "Goblin text"},
                    "content_hash": "hash-1",
                    "updated_at": "2026-03-11T21:00:00Z",
                    "updated_by": "tester",
                }
            ]
        }

    monkeypatch.setattr(web_services, "_fetch_mud_api_json", _fake_fetch)

    payload = web_services.build_policy_inventory_payload(
        policy_type=" species_block ",
        namespace=" image.blocks.species ",
        status=" draft ",
        session_id_override="session-1",
    )

    assert payload.item_count == 1
    assert payload.items[0].policy_id == "species_block:image.blocks.species:goblin"
    assert payload.filters == {
        "policy_type": "species_block",
        "namespace": "image.blocks.species",
        "status": "draft",
    }
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/policies"
    assert captured["query_params"] == {
        "policy_type": "species_block",
        "namespace": "image.blocks.species",
        "status": "draft",
    }


def test_build_policy_inventory_payload_rejects_invalid_item_shapes(monkeypatch) -> None:
    """Inventory builder should reject malformed mud-server payload contracts."""

    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id="s1",
        ),
    )

    monkeypatch.setattr(web_services, "_fetch_mud_api_json", lambda **_kwargs: {"items": "bad"})
    with pytest.raises(ValueError, match="must include 'items' list"):
        web_services.build_policy_inventory_payload(
            policy_type=None,
            namespace=None,
            status=None,
            session_id_override=None,
        )

    monkeypatch.setattr(web_services, "_fetch_mud_api_json", lambda **_kwargs: {"items": [1]})
    with pytest.raises(ValueError, match="must be JSON objects"):
        web_services.build_policy_inventory_payload(
            policy_type=None,
            namespace=None,
            status=None,
            session_id_override=None,
        )


def test_build_policy_detail_activation_and_publish_payloads(monkeypatch) -> None:
    """Detail/activation/publish builders should call expected mud API routes."""

    captured_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id=(session_id_override or "s1"),
        ),
    )

    def _fake_fetch(*, runtime, method, path, query_params):  # noqa: ANN001
        captured_calls.append(
            {
                "runtime": runtime,
                "method": method,
                "path": path,
                "query_params": query_params,
            }
        )
        if path.startswith("/api/policies/"):
            return {
                "policy_id": "species_block:image.blocks.species:goblin",
                "policy_type": "species_block",
                "namespace": "image.blocks.species",
                "policy_key": "goblin",
                "variant": "v1",
                "schema_version": "1.0",
                "policy_version": 4,
                "status": "draft",
                "content": {"text": "Goblin text"},
                "content_hash": "hash-1",
                "updated_at": "2026-03-11T21:00:00Z",
                "updated_by": "tester",
            }
        if path == "/api/policy-activations":
            return {
                "world_id": "pipeworks_web",
                "client_profile": "mobile",
                "items": [
                    {
                        "world_id": "pipeworks_web",
                        "client_profile": "mobile",
                        "policy_id": "species_block:image.blocks.species:goblin",
                        "variant": "v1",
                        "activated_at": "2026-03-11T21:00:00Z",
                        "activated_by": "tester",
                        "rollback_of_activation_id": None,
                        "audit_event_id": 101,
                    }
                ],
            }
        if path.startswith("/api/policy-publish/"):
            return {
                "publish_run_id": 9,
                "world_id": "pipeworks_web",
                "client_profile": "mobile",
                "actor": "tester",
                "created_at": "2026-03-11T21:00:00Z",
                "manifest": {"manifest_hash": "mhash"},
                "artifact": {"artifact_hash": "ahash", "artifact_path": "/tmp/export.json"},
            }
        raise AssertionError(f"Unexpected route: {path}")

    monkeypatch.setattr(web_services, "_fetch_mud_api_json", _fake_fetch)

    detail_payload = web_services.build_policy_object_detail_payload(
        policy_id="species_block:image.blocks.species:goblin/v1",
        variant=" v1 ",
        session_id_override="session-1",
    )
    assert detail_payload.variant == "v1"

    activation_payload = web_services.build_policy_activation_scope_payload(
        scope="pipeworks_web:mobile",
        effective=False,
        session_id_override="session-1",
    )
    assert activation_payload.world_id == "pipeworks_web"
    assert activation_payload.items[0]["policy_id"] == "species_block:image.blocks.species:goblin"

    publish_payload = web_services.build_policy_publish_run_payload(
        publish_run_id=9,
        session_id_override="session-1",
    )
    assert publish_payload.publish_run_id == 9

    assert (
        captured_calls[0]["path"]
        == "/api/policies/species_block%3Aimage.blocks.species%3Agoblin%2Fv1"
    )
    assert captured_calls[0]["query_params"] == {"variant": "v1"}
    assert captured_calls[1]["path"] == "/api/policy-activations"
    assert captured_calls[1]["query_params"] == {
        "scope": "pipeworks_web:mobile",
        "effective": "false",
    }
    assert captured_calls[2]["path"] == "/api/policy-publish/9"
