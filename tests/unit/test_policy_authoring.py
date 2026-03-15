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


def test_selector_from_relative_path_maps_prompt_text_files() -> None:
    """Versioned prompt text paths should map to canonical prompt selectors."""
    selector = policy_authoring.selector_from_relative_path("translation/prompts/ic/default_v1.txt")
    assert selector is not None
    assert selector.policy_type == "prompt"
    assert selector.namespace == "translation.prompts.ic"
    assert selector.policy_key == "default"
    assert selector.variant == "v1"
    assert selector.policy_id == "prompt:translation.prompts.ic:default"


def test_selector_from_relative_path_maps_tone_profile_json_files() -> None:
    """Tone profile JSON paths should map to canonical tone-profile selectors."""
    selector = policy_authoring.selector_from_relative_path(
        "image/tone_profiles/ledger_engraving_v1.json"
    )
    assert selector is not None
    assert selector.policy_type == "tone_profile"
    assert selector.namespace == "image.tone_profiles"
    assert selector.policy_key == "ledger_engraving"
    assert selector.variant == "v1"
    assert selector.policy_id == "tone_profile:image.tone_profiles:ledger_engraving"


def test_selector_from_relative_path_maps_descriptor_layer_structured_files() -> None:
    """Descriptor-layer YAML/JSON paths should map to canonical layer-2 selectors."""
    selector = policy_authoring.selector_from_relative_path(
        "image/descriptor_layers/id_card_v2.yaml"
    )
    assert selector is not None
    assert selector.policy_type == "descriptor_layer"
    assert selector.namespace == "image.descriptors"
    assert selector.policy_key == "id_card"
    assert selector.variant == "v2"
    assert selector.policy_id == "descriptor_layer:image.descriptors:id_card"


def test_selector_from_relative_path_maps_registry_yaml_files() -> None:
    """Registry YAML paths should map to canonical registry selectors."""
    versioned_selector = policy_authoring.selector_from_relative_path(
        "image/registries/species_registry_v3.yaml"
    )
    assert versioned_selector is not None
    assert versioned_selector.policy_type == "registry"
    assert versioned_selector.namespace == "image.registries"
    assert versioned_selector.policy_key == "species_registry"
    assert versioned_selector.variant == "v3"

    unversioned_selector = policy_authoring.selector_from_relative_path(
        "image/registries/species_registry.yaml"
    )
    assert unversioned_selector is not None
    assert unversioned_selector.policy_type == "registry"
    assert unversioned_selector.policy_key == "species_registry"
    assert unversioned_selector.variant == "v1"


def test_selector_from_relative_path_returns_none_for_unmapped_paths() -> None:
    """Non-versioned or unsupported paths should stay unmapped."""
    assert policy_authoring.selector_from_relative_path("image/prompts/portrait.txt") is None
    assert policy_authoring.selector_from_relative_path("image/blocks/species/bad.yaml") is None
    assert (
        policy_authoring.selector_from_relative_path("image/descriptor_layers/id_card_v1.txt")
        is None
    )


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
        raise AssertionError(f"Unexpected URL: {url}")  # pragma: no cover

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


def test_save_policy_variant_from_raw_content_supports_prompt_text(monkeypatch) -> None:
    """Generic save helper should serialize prompt text into canonical content payload."""
    selector = PolicySelector(
        policy_type="prompt",
        namespace="translation.prompts.ic",
        policy_key="default",
        variant="v1",
    )
    config = MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1")

    captured_payloads: list[dict[str, object | None]] = []

    def _fake_request_json(**kwargs):
        captured_payloads.append(kwargs.get("json_payload"))
        if "/validate" in kwargs["url"]:
            return {"is_valid": True, "validation_run_id": 12}
        if "/variants/" in kwargs["url"]:
            return {"policy_version": 5, "content_hash": "hash-prompt"}
        raise AssertionError(f"Unexpected URL: {kwargs['url']}")  # pragma: no cover

    monkeypatch.setattr(policy_authoring, "_request_json", _fake_request_json)
    monkeypatch.setattr(policy_authoring, "_resolve_next_policy_version", lambda **kwargs: 5)

    result = policy_authoring.save_policy_variant_from_raw_content(
        selector=selector,
        raw_content="  Stay in-character and terse.  \n",
        schema_version="1.0",
        status="candidate",
        activate=False,
        world_id=None,
        client_profile=None,
        actor="tester",
        runtime_config=config,
    )
    assert result.policy_id == "prompt:translation.prompts.ic:default"
    assert result.policy_version == 5
    assert result.content_hash == "hash-prompt"
    assert result.validation_run_id == 12
    assert captured_payloads[0]["content"] == {"text": "Stay in-character and terse."}
    assert captured_payloads[1]["content"] == {"text": "Stay in-character and terse."}


def test_save_policy_variant_from_raw_content_uses_resolved_next_version_for_requests(
    monkeypatch,
) -> None:
    """Save helper should use resolved next version for validate/upsert request payloads."""

    selector = PolicySelector(
        policy_type="prompt",
        namespace="translation.prompts.ic",
        policy_key="default",
        variant="v1",
    )
    config = MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1")

    captured_payloads: list[dict[str, object | None]] = []

    def _fake_request_json(**kwargs):
        captured_payloads.append(kwargs.get("json_payload"))
        if "/validate" in kwargs["url"]:
            return {"is_valid": True, "validation_run_id": 12}
        if "/variants/" in kwargs["url"]:
            # Canonical server response remains authoritative for returned version.
            return {"policy_version": 43, "content_hash": "hash-prompt"}
        raise AssertionError(f"Unexpected URL: {kwargs['url']}")  # pragma: no cover

    monkeypatch.setattr(policy_authoring, "_request_json", _fake_request_json)
    monkeypatch.setattr(policy_authoring, "_resolve_next_policy_version", lambda **kwargs: 42)

    result = policy_authoring.save_policy_variant_from_raw_content(
        selector=selector,
        raw_content="Stay in-character and terse.\n",
        schema_version="1.0",
        status="candidate",
        activate=False,
        world_id=None,
        client_profile=None,
        actor="tester",
        runtime_config=config,
    )

    assert captured_payloads[0]["policy_version"] == 42
    assert captured_payloads[1]["policy_version"] == 42
    assert result.policy_version == 43


def test_save_policy_variant_from_raw_content_trims_activation_scope_fields(monkeypatch) -> None:
    """Activation payload should normalize scope/operator fields before API call."""

    selector = PolicySelector(
        policy_type="species_block",
        namespace="image.blocks.species",
        policy_key="goblin",
        variant="v1",
    )
    config = MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1")

    captured_activation_payload: dict[str, object] = {}

    def _fake_request_json(**kwargs):
        if "/validate" in kwargs["url"]:
            return {"is_valid": True, "validation_run_id": 10}
        if "/variants/" in kwargs["url"]:
            return {"policy_version": 2, "content_hash": "hash-2"}
        if "/policy-activations" in kwargs["url"]:
            captured_activation_payload.update(kwargs.get("json_payload") or {})
            return {"audit_event_id": 77}
        raise AssertionError(f"Unexpected URL: {kwargs['url']}")  # pragma: no cover

    monkeypatch.setattr(policy_authoring, "_request_json", _fake_request_json)
    monkeypatch.setattr(policy_authoring, "_resolve_next_policy_version", lambda **kwargs: 2)

    result = policy_authoring.save_policy_variant_from_raw_content(
        selector=selector,
        raw_content="text: |\n  Canonical goblin text.\n",
        schema_version="1.0",
        status="candidate",
        activate=True,
        world_id=" pipeworks_web ",
        client_profile=" mobile ",
        actor=" tester ",
        runtime_config=config,
    )

    assert result.activation_audit_event_id == 77
    assert captured_activation_payload == {
        "world_id": "pipeworks_web",
        "client_profile": "mobile",
        "policy_id": "species_block:image.blocks.species:goblin",
        "variant": "v1",
        "activated_by": "tester",
    }


def test_save_policy_variant_from_raw_content_rejects_invalid_tone_profile_json() -> None:
    """Generic save helper should reject non-JSON tone profile payload text."""
    with pytest.raises(ValueError, match="must be valid JSON object text"):
        policy_authoring.save_policy_variant_from_raw_content(
            selector=PolicySelector(
                policy_type="tone_profile",
                namespace="image.tone_profiles",
                policy_key="ledger_engraving",
                variant="v1",
            ),
            raw_content="{not valid json}",
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


def test_save_policy_variant_from_raw_content_rejects_tone_profile_non_object_json() -> None:
    """Tone-profile save should reject valid JSON that is not an object payload."""
    with pytest.raises(ValueError, match="must be a JSON object"):
        policy_authoring.save_policy_variant_from_raw_content(
            selector=PolicySelector(
                policy_type="tone_profile",
                namespace="image.tone_profiles",
                policy_key="ledger_engraving",
                variant="v1",
            ),
            raw_content='["not-an-object"]',
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


def test_build_policy_content_from_raw_accepts_tone_profile_object_payload() -> None:
    """Tone-profile content builder should accept valid JSON object payload text."""
    content = policy_authoring._build_policy_content_from_raw(  # noqa: SLF001
        selector=PolicySelector(
            policy_type="tone_profile",
            namespace="image.tone_profiles",
            policy_key="ledger_engraving",
            variant="v1",
        ),
        raw_content='{"prompt_block":"Etched metallic texture."}',
    )
    assert content == {"prompt_block": "Etched metallic texture."}


def test_save_policy_variant_from_raw_content_supports_image_block_text(monkeypatch) -> None:
    """Generic save helper should serialize image-block text into canonical content payload."""
    selector = PolicySelector(
        policy_type="image_block",
        namespace="image.blocks.pose",
        policy_key="standing_front",
        variant="v1",
    )
    config = MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1")

    captured_payloads: list[dict[str, object | None]] = []

    def _fake_request_json(**kwargs):
        captured_payloads.append(kwargs.get("json_payload"))
        if "/validate" in kwargs["url"]:
            return {"is_valid": True, "validation_run_id": 12}
        if "/variants/" in kwargs["url"]:
            return {"policy_version": 5, "content_hash": "hash-image-block"}
        raise AssertionError(f"Unexpected URL: {kwargs['url']}")  # pragma: no cover

    monkeypatch.setattr(policy_authoring, "_request_json", _fake_request_json)
    monkeypatch.setattr(policy_authoring, "_resolve_next_policy_version", lambda **kwargs: 5)

    result = policy_authoring.save_policy_variant_from_raw_content(
        selector=selector,
        raw_content="  front-facing neutral stance  \n",
        schema_version="1.0",
        status="candidate",
        activate=False,
        world_id=None,
        client_profile=None,
        actor="tester",
        runtime_config=config,
    )
    assert result.policy_id == "image_block:image.blocks.pose:standing_front"
    assert result.policy_version == 5
    assert result.content_hash == "hash-image-block"
    assert result.validation_run_id == 12
    assert captured_payloads[0]["content"] == {"text": "front-facing neutral stance"}
    assert captured_payloads[1]["content"] == {"text": "front-facing neutral stance"}


def test_build_policy_content_from_raw_accepts_clothing_block_object_payload() -> None:
    """Clothing-block content builder should preserve structured object payloads."""
    content = policy_authoring._build_policy_content_from_raw(  # noqa: SLF001
        selector=PolicySelector(
            policy_type="clothing_block",
            namespace="image.blocks.clothing.activity",
            policy_key="clerical",
            variant="v1",
        ),
        raw_content='{"text":"Formal clerical attire.","slots":["torso","legs"]}',
    )
    assert content == {
        "text": "Formal clerical attire.",
        "slots": ["torso", "legs"],
    }


def test_save_policy_variant_from_raw_content_supports_clothing_block_object(monkeypatch) -> None:
    """Generic save helper should preserve clothing-block object payloads."""
    selector = PolicySelector(
        policy_type="clothing_block",
        namespace="image.blocks.clothing.activity",
        policy_key="clerical",
        variant="v1",
    )
    config = MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1")

    captured_payloads: list[dict[str, object | None]] = []

    def _fake_request_json(**kwargs):
        captured_payloads.append(kwargs.get("json_payload"))
        if "/validate" in kwargs["url"]:
            return {"is_valid": True, "validation_run_id": 19}
        if "/variants/" in kwargs["url"]:
            return {"policy_version": 7, "content_hash": "hash-clothing-block"}
        raise AssertionError(f"Unexpected URL: {kwargs['url']}")  # pragma: no cover

    monkeypatch.setattr(policy_authoring, "_request_json", _fake_request_json)
    monkeypatch.setattr(policy_authoring, "_resolve_next_policy_version", lambda **kwargs: 7)

    result = policy_authoring.save_policy_variant_from_raw_content(
        selector=selector,
        raw_content='{"text":"Formal clerical attire.","slots":["torso","legs"]}',
        schema_version="1.0",
        status="candidate",
        activate=False,
        world_id=None,
        client_profile=None,
        actor="tester",
        runtime_config=config,
    )
    assert result.policy_id == "clothing_block:image.blocks.clothing.activity:clerical"
    assert result.policy_version == 7
    assert result.content_hash == "hash-clothing-block"
    assert result.validation_run_id == 19
    assert captured_payloads[0]["content"] == {
        "text": "Formal clerical attire.",
        "slots": ["torso", "legs"],
    }
    assert captured_payloads[1]["content"] == {
        "text": "Formal clerical attire.",
        "slots": ["torso", "legs"],
    }


def test_save_policy_variant_from_raw_content_rejects_unsupported_policy_type() -> None:
    """Generic save helper should reject policy types outside implemented mappings."""
    with pytest.raises(ValueError, match="supports only policy_type values"):
        policy_authoring.save_policy_variant_from_raw_content(
            selector=PolicySelector(
                policy_type="manifest_bundle",
                namespace="image.manifests",
                policy_key="default",
                variant="v1",
            ),
            raw_content='{"references":[]}',
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


def test_save_policy_variant_from_raw_content_supports_descriptor_layer_references(
    monkeypatch,
) -> None:
    """Generic save helper should pass normalized references for descriptor-layer payloads."""
    selector = PolicySelector(
        policy_type="descriptor_layer",
        namespace="image.descriptors",
        policy_key="id_card",
        variant="v1",
    )
    config = MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1")

    captured_payloads: list[dict[str, object | None]] = []

    def _fake_request_json(**kwargs):
        captured_payloads.append(kwargs.get("json_payload"))
        if "/validate" in kwargs["url"]:
            return {"is_valid": True, "validation_run_id": 77}
        if "/variants/" in kwargs["url"]:
            return {"policy_version": 2, "content_hash": "hash-layer2"}
        raise AssertionError(f"Unexpected URL: {kwargs['url']}")  # pragma: no cover

    monkeypatch.setattr(policy_authoring, "_request_json", _fake_request_json)
    monkeypatch.setattr(policy_authoring, "_resolve_next_policy_version", lambda **kwargs: 2)

    result = policy_authoring.save_policy_variant_from_raw_content(
        selector=selector,
        raw_content=(
            "text: |\n"
            "  Identity card descriptor layer.\n"
            "references:\n"
            "  - policy_id: species_block:image.blocks.species:goblin\n"
            "    variant: v1\n"
        ),
        schema_version="1.0",
        status="candidate",
        activate=False,
        world_id=None,
        client_profile=None,
        actor="tester",
        runtime_config=config,
    )
    assert result.policy_id == "descriptor_layer:image.descriptors:id_card"
    assert result.policy_version == 2
    assert captured_payloads[0]["content"] == {
        "text": "Identity card descriptor layer.",
        "references": [
            {
                "policy_id": "species_block:image.blocks.species:goblin",
                "variant": "v1",
            }
        ],
    }


def test_save_policy_variant_from_raw_content_supports_registry_legacy_inference(
    monkeypatch,
) -> None:
    """Registry helper should infer references from legacy species block_path fields."""
    selector = PolicySelector(
        policy_type="registry",
        namespace="image.registries",
        policy_key="species_registry",
        variant="v1",
    )
    config = MudPolicyRuntimeConfig(base_url="http://mud.local:8000", session_id="s-1")

    captured_payloads: list[dict[str, object | None]] = []

    def _fake_request_json(**kwargs):
        captured_payloads.append(kwargs.get("json_payload"))
        if "/validate" in kwargs["url"]:
            return {"is_valid": True, "validation_run_id": 32}
        if "/variants/" in kwargs["url"]:
            return {"policy_version": 1, "content_hash": "hash-registry"}
        raise AssertionError(f"Unexpected URL: {kwargs['url']}")  # pragma: no cover

    monkeypatch.setattr(policy_authoring, "_request_json", _fake_request_json)
    monkeypatch.setattr(policy_authoring, "_resolve_next_policy_version", lambda **kwargs: 1)

    result = policy_authoring.save_policy_variant_from_raw_content(
        selector=selector,
        raw_content=(
            "entries:\n"
            "  - block_path: policies/image/blocks/species/goblin_v1.yaml\n"
            "  - block_path: policies/image/blocks/species/human_v2.yaml\n"
        ),
        schema_version="1.0",
        status="candidate",
        activate=False,
        world_id=None,
        client_profile=None,
        actor="tester",
        runtime_config=config,
    )
    assert result.policy_id == "registry:image.registries:species_registry"
    assert captured_payloads[0]["content"] == {
        "references": [
            {"policy_id": "species_block:image.blocks.species:goblin", "variant": "v1"},
            {"policy_id": "species_block:image.blocks.species:human", "variant": "v2"},
        ]
    }


def test_save_policy_variant_from_raw_content_rejects_registry_without_references() -> None:
    """Registry payloads without explicit/inferable references should be rejected."""
    with pytest.raises(ValueError, match="registry content must include references"):
        policy_authoring.save_policy_variant_from_raw_content(
            selector=PolicySelector(
                policy_type="registry",
                namespace="image.registries",
                policy_key="clothing_registry",
                variant="v1",
            ),
            raw_content="registry:\n  id: clothing_registry\n",
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


def test_save_policy_variant_from_raw_content_rejects_descriptor_layer_non_object_payload() -> None:
    """Descriptor-layer save should reject structured payloads that are not mapping objects."""
    with pytest.raises(ValueError, match="descriptor_layer raw_content must be a YAML/JSON object"):
        policy_authoring.save_policy_variant_from_raw_content(
            selector=PolicySelector(
                policy_type="descriptor_layer",
                namespace="image.descriptors",
                policy_key="id_card",
                variant="v1",
            ),
            raw_content='["not-an-object"]',
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


def test_save_policy_variant_from_raw_content_rejects_descriptor_layer_without_text() -> None:
    """Descriptor-layer save should fail fast when content.text is missing/blank."""
    with pytest.raises(
        ValueError,
        match="descriptor_layer content.text must be a non-empty string",
    ):
        policy_authoring.save_policy_variant_from_raw_content(
            selector=PolicySelector(
                policy_type="descriptor_layer",
                namespace="image.descriptors",
                policy_key="id_card",
                variant="v1",
            ),
            raw_content=(
                "references:\n"
                "  - policy_id: species_block:image.blocks.species:goblin\n"
                "    variant: v1\n"
            ),
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


def test_layer2_parsing_helpers_cover_error_branches() -> None:
    """Layer 2 parsing helpers should report stable errors for malformed payloads."""
    with pytest.raises(ValueError, match="descriptor_layer content must include"):
        policy_authoring._extract_layer2_references(  # noqa: SLF001
            payload={},
            policy_type="descriptor_layer",
        )

    with pytest.raises(ValueError, match="content.references must be a non-empty list"):
        policy_authoring._normalize_reference_entries(  # noqa: SLF001
            references=[],
            policy_type="registry",
        )

    with pytest.raises(ValueError, match="must be an object with 'policy_id' and 'variant'"):
        policy_authoring._normalize_reference_entries(  # noqa: SLF001
            references=[42],
            policy_type="registry",
        )

    with pytest.raises(ValueError, match="policy_id is required"):
        policy_authoring._normalize_reference_entries(  # noqa: SLF001
            references=[{"policy_id": "", "variant": "v1"}],
            policy_type="registry",
        )

    with pytest.raises(ValueError, match="variant is required"):
        policy_authoring._normalize_reference_entries(  # noqa: SLF001
            references=[{"policy_id": "species_block:image.blocks.species:goblin", "variant": ""}],
            policy_type="registry",
        )


def test_registry_inference_helpers_cover_slots_duplicates_and_unresolved_paths() -> None:
    """Registry inference should skip invalid/duplicate/unresolved path candidates."""
    inferred = policy_authoring._infer_registry_references_from_legacy_payload(  # noqa: SLF001
        payload={
            "entries": [
                42,
                {"block_path": "policies/image/blocks/species/goblin_v1.yaml"},
                {"block_path": "image/blocks/clothing/workwear_v1.txt"},
            ],
            "slots": {
                "environment": [
                    {"block_path": "policies/image/blocks/species/goblin_v1.yaml"},
                    {"prompt_path": "translation/prompts/ic/default_v2.txt"},
                ]
            },
        }
    )
    assert inferred == [
        {"policy_id": "species_block:image.blocks.species:goblin", "variant": "v1"},
        {"policy_id": "prompt:translation.prompts.ic:default", "variant": "v2"},
    ]


def test_policy_reference_from_legacy_path_maps_supported_layer1_paths() -> None:
    """Legacy path mapper should resolve known Layer 1 file families."""
    assert policy_authoring._policy_reference_from_legacy_path(  # noqa: SLF001
        "policies/image/blocks/species/goblin_v1.yaml"
    ) == {
        "policy_id": "species_block:image.blocks.species:goblin",
        "variant": "v1",
    }
    assert policy_authoring._policy_reference_from_legacy_path(  # noqa: SLF001
        "translation/prompts/ic/default_v2.txt"
    ) == {
        "policy_id": "prompt:translation.prompts.ic:default",
        "variant": "v2",
    }
    assert policy_authoring._policy_reference_from_legacy_path(  # noqa: SLF001
        "image/tone_profiles/ledger_engraving_v1.json"
    ) == {
        "policy_id": "tone_profile:image.tone_profiles:ledger_engraving",
        "variant": "v1",
    }
    assert (
        policy_authoring._policy_reference_from_legacy_path("image/blocks/clothing/workwear_v1.txt")
        is None
    )  # noqa: SLF001


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
