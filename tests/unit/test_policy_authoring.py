"""Unit tests for Phase 2 policy authoring helpers."""

from __future__ import annotations

from types import SimpleNamespace

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
