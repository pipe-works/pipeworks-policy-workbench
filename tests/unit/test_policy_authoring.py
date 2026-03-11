"""Unit tests for Phase 2 policy authoring helpers."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from policy_workbench import policy_authoring
from policy_workbench.policy_authoring import MudPolicyRuntimeConfig, PolicySelector


def test_selector_from_relative_path_maps_species_block_files() -> None:
    """Species block YAML paths should map to canonical selector fields."""
    selector = policy_authoring.selector_from_relative_path("image/blocks/species/goblin_v1.yaml")
    assert selector is not None
    assert selector.policy_type == "species_block"
    assert selector.namespace == "image.blocks.species"
    assert selector.policy_key == "goblin"
    assert selector.variant == "v1"
    assert selector.policy_id == "species_block:image.blocks.species:goblin"


def test_selector_from_relative_path_returns_none_for_non_pilot_paths() -> None:
    """Non-pilot or non-species paths should stay unmapped in Phase 2."""
    assert policy_authoring.selector_from_relative_path("image/prompts/portrait.txt") is None
    assert policy_authoring.selector_from_relative_path("image/blocks/species/bad.yaml") is None


def test_resolve_runtime_config_uses_env_and_requires_session(monkeypatch) -> None:
    """Runtime config resolver should enforce non-empty session id contract."""
    monkeypatch.setenv("PW_POLICY_MUD_API_BASE_URL", "http://mud.local:8000")
    monkeypatch.setenv("PW_POLICY_MUD_SESSION_ID", "session-123")
    config = policy_authoring.resolve_runtime_config()
    assert config.base_url == "http://mud.local:8000"
    assert config.session_id == "session-123"

    monkeypatch.delenv("PW_POLICY_MUD_SESSION_ID", raising=False)
    with pytest.raises(ValueError, match="session id is required"):
        policy_authoring.resolve_runtime_config()


def test_save_species_block_from_yaml_runs_validate_then_upsert_then_activate(monkeypatch) -> None:
    """Save helper should orchestrate validate/save/activate in fixed order."""
    selector = PolicySelector(
        policy_type="species_block",
        namespace="image.blocks.species",
        policy_key="goblin",
        variant="v1",
    )
    config = MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1")

    calls: list[str] = []

    def _fake_request_json(**kwargs):
        url = kwargs["url"]
        calls.append(url)
        if "/validate" in url:
            return {"is_valid": True, "validation_run_id": 10}
        if "/variants/" in url:
            return {"policy_version": 4, "content_hash": "hash-4"}
        if "/policy-activations" in url:
            return {"audit_event_id": 500}
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(policy_authoring, "_request_json", _fake_request_json)
    monkeypatch.setattr(policy_authoring, "_resolve_next_policy_version", lambda **kwargs: 4)

    result = policy_authoring.save_species_block_from_yaml(
        selector=selector,
        raw_yaml="text: |\n  Canonical goblin text.\n",
        schema_version="1.0",
        status="candidate",
        activate=True,
        world_id="pipeworks_web",
        client_profile="mobile",
        actor="tester",
        runtime_config=config,
    )
    assert result.policy_id == "species_block:image.blocks.species:goblin"
    assert result.variant == "v1"
    assert result.policy_version == 4
    assert result.content_hash == "hash-4"
    assert result.validation_run_id == 10
    assert result.activation_audit_event_id == 500
    assert any("/validate" in call for call in calls)
    assert any("/variants/" in call for call in calls)
    assert any("/policy-activations" in call for call in calls)


def test_save_species_block_from_yaml_requires_world_scope_for_activation(monkeypatch) -> None:
    """Activation mode should fail fast when ``world_id`` is missing."""
    selector = PolicySelector(
        policy_type="species_block",
        namespace="image.blocks.species",
        policy_key="goblin",
        variant="v1",
    )
    config = MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1")
    monkeypatch.setattr(policy_authoring, "_resolve_next_policy_version", lambda **kwargs: 1)
    monkeypatch.setattr(
        policy_authoring,
        "_request_json",
        lambda **kwargs: (
            {"is_valid": True, "validation_run_id": 1}
            if "/validate" in kwargs["url"]
            else {"policy_version": 1, "content_hash": "hash-1"}
        ),
    )

    with pytest.raises(ValueError, match="world_id is required"):
        policy_authoring.save_species_block_from_yaml(
            selector=selector,
            raw_yaml="text: |\n  Canonical goblin text.\n",
            schema_version="1.0",
            status="draft",
            activate=True,
            world_id=None,
            client_profile=None,
            actor=None,
            runtime_config=config,
        )


def test_resolve_next_policy_version_uses_not_found_as_initial(monkeypatch) -> None:
    """Version helper should start at 1 when mud-server returns not found."""
    monkeypatch.setattr(policy_authoring, "_request_json", lambda **kwargs: None)
    version = policy_authoring._resolve_next_policy_version(  # noqa: SLF001
        runtime_config=MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1"),
        policy_id="species_block:image.blocks.species:goblin",
        variant="v1",
    )
    assert version == 1


def test_resolve_next_policy_version_increments_existing_value(monkeypatch) -> None:
    """Version helper should increment existing policy_version values."""
    monkeypatch.setattr(
        policy_authoring,
        "_request_json",
        lambda **kwargs: {"policy_version": "7"},
    )
    version = policy_authoring._resolve_next_policy_version(  # noqa: SLF001
        runtime_config=MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1"),
        policy_id="species_block:image.blocks.species:goblin",
        variant="v1",
    )
    assert version == 8


def test_http_error_detail_prefers_contract_payload_fields() -> None:
    """HTTP error detail helper should favor ``code`` + ``detail`` payloads."""

    class _FakeHttpError:
        code = 422

        def read(self) -> bytes:
            return b'{"code":"POLICY_VALIDATION_ERROR","detail":"invalid"}'

    assert (
        policy_authoring._http_error_detail(
            SimpleNamespace(code=422, read=lambda: b"{}")
        )  # noqa: SLF001
        == "HTTP 422"
    )
    assert (
        policy_authoring._http_error_detail(_FakeHttpError())  # noqa: SLF001
        == "POLICY_VALIDATION_ERROR: invalid"
    )
    assert (
        policy_authoring._http_error_detail(
            SimpleNamespace(code=422, read=lambda: b'{"detail":"plain detail"}')
        )  # noqa: SLF001
        == "plain detail"
    )
    assert (
        policy_authoring._http_error_detail(
            SimpleNamespace(code=422, read=lambda: (_ for _ in ()).throw(OSError("boom")))
        )  # noqa: SLF001
        == "HTTP 422"
    )


def test_save_species_block_from_yaml_rejects_non_species_policy_type() -> None:
    """Save helper should reject selector policy types outside species pilot."""
    with pytest.raises(ValueError, match="supports only policy_type='species_block'"):
        policy_authoring.save_species_block_from_yaml(
            selector=PolicySelector(
                policy_type="prompt",
                namespace="image.prompts",
                policy_key="scene",
                variant="v1",
            ),
            raw_yaml="text: |\n  Prompt text.\n",
            schema_version="1.0",
            status="draft",
            activate=False,
            world_id=None,
            client_profile=None,
            actor=None,
            runtime_config=MudPolicyRuntimeConfig(
                base_url="http://mud.local:8000", session_id="s-1"
            ),
        )


def test_save_species_block_from_yaml_handles_validation_failure_branches(monkeypatch) -> None:
    """Validation failures should propagate deterministic error messages."""
    selector = PolicySelector(
        policy_type="species_block",
        namespace="image.blocks.species",
        policy_key="goblin",
        variant="v1",
    )
    config = MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1")
    monkeypatch.setattr(policy_authoring, "_resolve_next_policy_version", lambda **kwargs: 1)

    # Branch 1: validation payload unexpectedly missing.
    monkeypatch.setattr(policy_authoring, "_request_json", lambda **kwargs: None)
    with pytest.raises(ValueError, match="Validation request returned no payload"):
        policy_authoring.save_species_block_from_yaml(
            selector=selector,
            raw_yaml="text: |\n  Canonical goblin text.\n",
            schema_version="1.0",
            status="draft",
            activate=False,
            world_id=None,
            client_profile=None,
            actor=None,
            runtime_config=config,
        )

    # Branch 2: validation returns explicit error list.
    monkeypatch.setattr(
        policy_authoring,
        "_request_json",
        lambda **kwargs: {"is_valid": False, "errors": ["bad one", "bad two"]},
    )
    with pytest.raises(ValueError, match="bad one; bad two"):
        policy_authoring.save_species_block_from_yaml(
            selector=selector,
            raw_yaml="text: |\n  Canonical goblin text.\n",
            schema_version="1.0",
            status="draft",
            activate=False,
            world_id=None,
            client_profile=None,
            actor=None,
            runtime_config=config,
        )

    # Branch 3: validation invalid without usable errors list.
    monkeypatch.setattr(
        policy_authoring,
        "_request_json",
        lambda **kwargs: {"is_valid": False, "errors": []},
    )
    with pytest.raises(ValueError, match="Validation failed for policy payload"):
        policy_authoring.save_species_block_from_yaml(
            selector=selector,
            raw_yaml="text: |\n  Canonical goblin text.\n",
            schema_version="1.0",
            status="draft",
            activate=False,
            world_id=None,
            client_profile=None,
            actor=None,
            runtime_config=config,
        )


def test_save_species_block_from_yaml_rejects_missing_upsert_or_activation_payload(
    monkeypatch,
) -> None:
    """Save helper should fail when mandatory upsert/activation payloads are absent."""
    selector = PolicySelector(
        policy_type="species_block",
        namespace="image.blocks.species",
        policy_key="goblin",
        variant="v1",
    )
    config = MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1")
    monkeypatch.setattr(policy_authoring, "_resolve_next_policy_version", lambda **kwargs: 1)

    # Missing upsert payload after valid validation.
    responses = iter([{"is_valid": True, "validation_run_id": 1}, None])
    monkeypatch.setattr(policy_authoring, "_request_json", lambda **kwargs: next(responses))
    with pytest.raises(ValueError, match="Upsert request returned no payload"):
        policy_authoring.save_species_block_from_yaml(
            selector=selector,
            raw_yaml="text: |\n  Canonical goblin text.\n",
            schema_version="1.0",
            status="draft",
            activate=False,
            world_id=None,
            client_profile=None,
            actor=None,
            runtime_config=config,
        )

    # Missing activation payload in activate=true mode.
    responses = iter(
        [
            {"is_valid": True, "validation_run_id": 1},
            {"policy_version": 1, "content_hash": "h1"},
            None,
        ]
    )
    monkeypatch.setattr(policy_authoring, "_request_json", lambda **kwargs: next(responses))
    with pytest.raises(ValueError, match="Activation request returned no payload"):
        policy_authoring.save_species_block_from_yaml(
            selector=selector,
            raw_yaml="text: |\n  Canonical goblin text.\n",
            schema_version="1.0",
            status="draft",
            activate=True,
            world_id="pipeworks_web",
            client_profile=None,
            actor=None,
            runtime_config=config,
        )


def test_resolve_runtime_config_rejects_empty_base_url(monkeypatch) -> None:
    """Runtime config resolver should fail when base URL resolves to empty."""
    monkeypatch.setenv("PW_POLICY_MUD_API_BASE_URL", "   ")
    monkeypatch.setenv("PW_POLICY_MUD_SESSION_ID", "session-123")
    with pytest.raises(ValueError, match="base URL must not be empty"):
        policy_authoring.resolve_runtime_config()


def test_request_json_handles_success_not_found_and_transport_errors(monkeypatch) -> None:
    """Request helper should cover success, 404 passthrough, and transport failures."""

    class _FakeHttpResponse:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._payload

    monkeypatch.setattr(
        policy_authoring,
        "urlopen",
        lambda request, timeout=8.0: _FakeHttpResponse(b'{"ok": true}'),
    )
    assert policy_authoring._request_json(  # noqa: SLF001
        method="GET",
        url="http://mud.local/api/test",
        timeout_seconds=8.0,
    ) == {"ok": True}

    not_found_error = HTTPError(
        url="http://mud.local/api/test",
        code=404,
        msg="not found",
        hdrs=None,
        fp=BytesIO(b"{}"),
    )
    monkeypatch.setattr(
        policy_authoring, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(not_found_error)
    )
    assert (
        policy_authoring._request_json(  # noqa: SLF001
            method="GET",
            url="http://mud.local/api/test",
            timeout_seconds=8.0,
            allow_not_found=True,
        )
        is None
    )

    http_error = HTTPError(
        url="http://mud.local/api/test",
        code=422,
        msg="bad request",
        hdrs=None,
        fp=BytesIO(b'{"code":"POLICY_VALIDATION_ERROR","detail":"invalid"}'),
    )
    monkeypatch.setattr(
        policy_authoring, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(http_error)
    )
    with pytest.raises(ValueError, match="POLICY_VALIDATION_ERROR: invalid"):
        policy_authoring._request_json(  # noqa: SLF001
            method="POST",
            url="http://mud.local/api/test",
            timeout_seconds=8.0,
        )

    monkeypatch.setattr(
        policy_authoring,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(URLError("down")),
    )
    with pytest.raises(ValueError, match="Mud policy API request failed"):
        policy_authoring._request_json(  # noqa: SLF001
            method="GET",
            url="http://mud.local/api/test",
            timeout_seconds=8.0,
        )


def test_request_json_encodes_json_payload_when_provided(monkeypatch) -> None:
    """Request helper should attach JSON body/headers for payload requests."""

    class _FakeHttpResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"ok": true}'

    captured = {}

    def _fake_urlopen(request, timeout=8.0):
        captured["data"] = request.data
        captured["content_type"] = request.get_header("Content-type")
        return _FakeHttpResponse()

    monkeypatch.setattr(policy_authoring, "urlopen", _fake_urlopen)
    payload = {"status": "draft"}
    result = policy_authoring._request_json(  # noqa: SLF001
        method="POST",
        url="http://mud.local/api/test",
        timeout_seconds=8.0,
        json_payload=payload,
    )
    assert result == {"ok": True}
    assert captured["data"] == b'{"status": "draft"}'
    assert captured["content_type"] == "application/json"


def test_request_json_rejects_non_object_payloads(monkeypatch) -> None:
    """Request helper should reject non-dict JSON payloads."""

    class _FakeHttpResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b"[]"

    monkeypatch.setattr(policy_authoring, "urlopen", lambda *args, **kwargs: _FakeHttpResponse())
    with pytest.raises(ValueError, match="was not a JSON object"):
        policy_authoring._request_json(  # noqa: SLF001
            method="GET",
            url="http://mud.local/api/test",
            timeout_seconds=8.0,
        )
