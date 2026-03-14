"""Policy-object authoring helpers for Phase 2 API-only workflows.

This module is the bridge between workbench editing and mud-server canonical
policy APIs. It provides:
- deterministic mapping from canonical relative paths to policy selectors
- mud-server request orchestration for validate -> save -> optional activate
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote
from urllib.request import urlopen

import yaml  # type: ignore[import-untyped]

from . import mud_api_client
from .extractors import extract_yaml_text_field
from .mud_api_runtime import resolve_mud_api_runtime_config

_DEFAULT_MUD_API_BASE_URL = "http://127.0.0.1:8000"
_MUD_API_BASE_URL_ENV = "PW_POLICY_MUD_API_BASE_URL"
_MUD_API_SESSION_ID_ENV = "PW_POLICY_MUD_SESSION_ID"

# Selector mappings from relative file paths to canonical policy object identity.
_SPECIES_BLOCK_PATH_PATTERN = re.compile(
    r"^image/blocks/species/(?P<policy_key>.+)_(?P<variant>v[0-9][A-Za-z0-9_-]*)\.ya?ml$"
)
_PROMPT_TEXT_PATH_PATTERN = re.compile(
    r"^(?P<namespace_path>(?:image|translation)/prompts(?:/[A-Za-z0-9._-]+)*)/"
    r"(?P<policy_key>.+)_(?P<variant>v[0-9][A-Za-z0-9_-]*)\.txt$"
)
_TONE_PROFILE_PATH_PATTERN = re.compile(
    r"^image/tone_profiles/(?P<policy_key>.+)_(?P<variant>v[0-9][A-Za-z0-9_-]*)\.json$"
)
_DESCRIPTOR_LAYER_PATH_PATTERN = re.compile(
    r"^image/descriptor_layers/(?P<policy_key>.+)_(?P<variant>v[0-9][A-Za-z0-9_-]*)"
    r"\.(?:ya?ml|json)$"
)
_REGISTRY_VERSIONED_PATH_PATTERN = re.compile(
    r"^image/registries/(?P<policy_key>.+)_(?P<variant>v[0-9][A-Za-z0-9_-]*)\.ya?ml$"
)
_REGISTRY_UNVERSIONED_PATH_PATTERN = re.compile(r"^image/registries/(?P<policy_key>.+)\.ya?ml$")

_LEGACY_SPECIES_BLOCK_PATH_PATTERN = re.compile(
    r"^(?:policies/)?image/blocks/species/(?P<policy_key>.+)_"
    r"(?P<variant>v[0-9][A-Za-z0-9_-]*)\.ya?ml$"
)
_LEGACY_PROMPT_PATH_PATTERN = re.compile(
    r"^(?:policies/)?(?P<namespace_path>(?:image|translation)/prompts(?:/[A-Za-z0-9._-]+)*)/"
    r"(?P<policy_key>.+)_(?P<variant>v[0-9][A-Za-z0-9_-]*)\.txt$"
)
_LEGACY_TONE_PROFILE_PATH_PATTERN = re.compile(
    r"^(?:policies/)?image/tone_profiles/(?P<policy_key>.+)_"
    r"(?P<variant>v[0-9][A-Za-z0-9_-]*)\.json$"
)


@dataclass(frozen=True, slots=True)
class PolicySelector:
    """Canonical policy selector tuple used by workbench authoring flows."""

    policy_type: str
    namespace: str
    policy_key: str
    variant: str

    @property
    def policy_id(self) -> str:
        """Return canonical ``policy_type:namespace:policy_key`` identifier."""
        return f"{self.policy_type}:{self.namespace}:{self.policy_key}"


@dataclass(frozen=True, slots=True)
class MudPolicyRuntimeConfig:
    """Runtime config for mud-server API calls initiated by workbench."""

    base_url: str
    session_id: str
    timeout_seconds: float = 8.0


@dataclass(frozen=True, slots=True)
class PolicySaveResult:
    """Normalized save result returned after validate -> write -> activate."""

    policy_id: str
    variant: str
    policy_version: int
    content_hash: str
    validation_run_id: int
    activation_audit_event_id: int | None


def selector_from_relative_path(relative_path: str) -> PolicySelector | None:
    """Resolve canonical policy selector for a workbench relative path.

    Authorable mappings currently include:
    - ``species_block`` YAML blocks under ``image/blocks/species``
    - ``descriptor_layer`` structured files under ``image/descriptor_layers``
    - ``registry`` YAML files under ``image/registries``
    - versioned ``prompt`` text files under ``*/prompts/**``
    - ``tone_profile`` JSON files under ``image/tone_profiles``
    """
    normalized = relative_path.strip().replace("\\", "/")
    species_match = _SPECIES_BLOCK_PATH_PATTERN.fullmatch(normalized)
    if species_match is not None:
        return PolicySelector(
            policy_type="species_block",
            namespace="image.blocks.species",
            policy_key=species_match.group("policy_key"),
            variant=species_match.group("variant"),
        )

    prompt_match = _PROMPT_TEXT_PATH_PATTERN.fullmatch(normalized)
    if prompt_match is not None:
        namespace = prompt_match.group("namespace_path").replace("/", ".")
        return PolicySelector(
            policy_type="prompt",
            namespace=namespace,
            policy_key=prompt_match.group("policy_key"),
            variant=prompt_match.group("variant"),
        )

    tone_match = _TONE_PROFILE_PATH_PATTERN.fullmatch(normalized)
    if tone_match is not None:
        return PolicySelector(
            policy_type="tone_profile",
            namespace="image.tone_profiles",
            policy_key=tone_match.group("policy_key"),
            variant=tone_match.group("variant"),
        )

    descriptor_match = _DESCRIPTOR_LAYER_PATH_PATTERN.fullmatch(normalized)
    if descriptor_match is not None:
        return PolicySelector(
            policy_type="descriptor_layer",
            namespace="image.descriptor_layers",
            policy_key=descriptor_match.group("policy_key"),
            variant=descriptor_match.group("variant"),
        )

    registry_versioned_match = _REGISTRY_VERSIONED_PATH_PATTERN.fullmatch(normalized)
    if registry_versioned_match is not None:
        return PolicySelector(
            policy_type="registry",
            namespace="image.registries",
            policy_key=registry_versioned_match.group("policy_key"),
            variant=registry_versioned_match.group("variant"),
        )

    registry_unversioned_match = _REGISTRY_UNVERSIONED_PATH_PATTERN.fullmatch(normalized)
    if registry_unversioned_match is not None:
        return PolicySelector(
            policy_type="registry",
            namespace="image.registries",
            policy_key=registry_unversioned_match.group("policy_key"),
            variant="v1",
        )

    return None


def save_policy_variant_from_raw_content(
    *,
    selector: PolicySelector,
    raw_content: str,
    schema_version: str,
    status: str,
    activate: bool,
    world_id: str | None,
    client_profile: str | None,
    actor: str | None,
    runtime_config: MudPolicyRuntimeConfig,
) -> PolicySaveResult:
    """Save one policy variant through mud-server canonical policy APIs.

    Save order is fixed:
    1. Determine next ``policy_version`` from current variant state.
    2. Validate candidate payload.
    3. Upsert variant only when validation succeeds.
    4. Optionally update activation pointer for provided scope.
    """
    content = _build_policy_content_from_raw(selector=selector, raw_content=raw_content)
    policy_id = selector.policy_id
    next_policy_version = _resolve_next_policy_version(
        runtime_config=runtime_config,
        policy_id=policy_id,
        variant=selector.variant,
    )

    validate_payload = _request_json(
        method="POST",
        url=(
            f"{runtime_config.base_url}/api/policies/{quote(policy_id, safe='')}/validate"
            f"?session_id={quote(runtime_config.session_id, safe='')}"
            f"&variant={quote(selector.variant, safe='')}"
        ),
        timeout_seconds=runtime_config.timeout_seconds,
        json_payload={
            "schema_version": schema_version,
            "policy_version": next_policy_version,
            "status": status,
            "content": content,
            "validated_by": actor,
        },
    )
    if validate_payload is None:
        raise ValueError("Validation request returned no payload.")
    if not bool(validate_payload.get("is_valid", False)):
        errors = validate_payload.get("errors") or []
        if isinstance(errors, list) and errors:
            raise ValueError("; ".join(str(item) for item in errors))
        raise ValueError("Validation failed for policy payload.")

    upsert_payload = _request_json(
        method="PUT",
        url=(
            f"{runtime_config.base_url}/api/policies/{quote(policy_id, safe='')}"
            f"/variants/{quote(selector.variant, safe='')}"
            f"?session_id={quote(runtime_config.session_id, safe='')}"
        ),
        timeout_seconds=runtime_config.timeout_seconds,
        json_payload={
            "schema_version": schema_version,
            "policy_version": next_policy_version,
            "status": status,
            "content": content,
            "updated_by": actor,
        },
    )
    if upsert_payload is None:
        raise ValueError("Upsert request returned no payload.")

    activation_audit_event_id: int | None = None
    if activate:
        if not (world_id or "").strip():
            raise ValueError("world_id is required when activate=true.")

        activation_request: dict[str, object] = {
            "world_id": str(world_id).strip(),
            "policy_id": policy_id,
            "variant": selector.variant,
        }
        if (client_profile or "").strip():
            activation_request["client_profile"] = str(client_profile).strip()
        if (actor or "").strip():
            activation_request["activated_by"] = str(actor).strip()

        activation_payload = _request_json(
            method="POST",
            url=(
                f"{runtime_config.base_url}/api/policy-activations"
                f"?session_id={quote(runtime_config.session_id, safe='')}"
            ),
            timeout_seconds=runtime_config.timeout_seconds,
            json_payload=activation_request,
        )
        if activation_payload is None:
            raise ValueError("Activation request returned no payload.")
        raw_event_id = activation_payload.get("audit_event_id")
        activation_audit_event_id = (
            int(cast(int | str, raw_event_id)) if raw_event_id is not None else None
        )

    return PolicySaveResult(
        policy_id=policy_id,
        variant=selector.variant,
        policy_version=int(cast(int | str, upsert_payload["policy_version"])),
        content_hash=str(upsert_payload["content_hash"]),
        validation_run_id=int(cast(int | str, validate_payload["validation_run_id"])),
        activation_audit_event_id=activation_audit_event_id,
    )


def save_species_block_from_yaml(
    *,
    selector: PolicySelector,
    raw_yaml: str,
    schema_version: str,
    status: str,
    activate: bool,
    world_id: str | None,
    client_profile: str | None,
    actor: str | None,
    runtime_config: MudPolicyRuntimeConfig,
) -> PolicySaveResult:
    """Backward-compatible species helper used by existing call sites/tests.

    ``save_policy_variant_from_raw_content`` is the generalized Phase 5 entry
    point. This wrapper preserves the prior explicit guard for callers that
    still use the legacy species-specific function name.
    """
    if selector.policy_type != "species_block":
        raise ValueError("Phase 2 save currently supports only policy_type='species_block'.")
    return save_policy_variant_from_raw_content(
        selector=selector,
        raw_content=raw_yaml,
        schema_version=schema_version,
        status=status,
        activate=activate,
        world_id=world_id,
        client_profile=client_profile,
        actor=actor,
        runtime_config=runtime_config,
    )


def resolve_runtime_config(
    *,
    session_id_override: str | None = None,
    base_url_override: str | None = None,
) -> MudPolicyRuntimeConfig:
    """Resolve mud-server API runtime config from env and optional overrides."""
    shared_config = resolve_mud_api_runtime_config(
        session_id_override=session_id_override,
        base_url_override=base_url_override,
        base_url_env_var=_MUD_API_BASE_URL_ENV,
        session_id_env_var=_MUD_API_SESSION_ID_ENV,
        default_base_url=_DEFAULT_MUD_API_BASE_URL,
        empty_base_url_error="Mud policy API base URL must not be empty.",
        missing_session_error=(
            "Mud policy session id is required. Set PW_POLICY_MUD_SESSION_ID or pass session_id."
        ),
    )
    return MudPolicyRuntimeConfig(
        base_url=shared_config.base_url,
        session_id=shared_config.session_id,
        timeout_seconds=shared_config.timeout_seconds,
    )


def _resolve_next_policy_version(
    *,
    runtime_config: MudPolicyRuntimeConfig,
    policy_id: str,
    variant: str,
) -> int:
    """Read current variant state and return the next policy version number."""
    response = _request_json(
        method="GET",
        url=(
            f"{runtime_config.base_url}/api/policies/{quote(policy_id, safe='')}"
            f"?session_id={quote(runtime_config.session_id, safe='')}"
            f"&variant={quote(variant, safe='')}"
        ),
        timeout_seconds=runtime_config.timeout_seconds,
        allow_not_found=True,
    )
    if response is None:
        return 1
    raw_policy_version = response.get("policy_version", 0)
    return int(cast(int | str, raw_policy_version)) + 1


def _build_policy_content_from_raw(
    *,
    selector: PolicySelector,
    raw_content: str,
) -> dict[str, object]:
    """Build contract ``content`` payload for one selector type.

    The workbench remains an API client, so this helper only transforms file
    content into canonical request payload shape. Policy-type validity is
    ultimately enforced by mud-server validation endpoints.
    """
    if selector.policy_type == "species_block":
        return {"text": extract_yaml_text_field(raw_content)}

    if selector.policy_type == "prompt":
        return {"text": raw_content.strip()}

    if selector.policy_type == "image_block":
        return {"text": raw_content.strip()}

    if selector.policy_type == "tone_profile":
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ValueError("tone_profile raw_content must be valid JSON object text.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("tone_profile raw_content must be a JSON object.")
        return cast(dict[str, object], parsed)

    if selector.policy_type in {"descriptor_layer", "registry"}:
        payload = _parse_structured_object_from_raw(
            raw_content=raw_content,
            policy_type=selector.policy_type,
        )
        references = _extract_layer2_references(
            payload=payload,
            policy_type=selector.policy_type,
        )
        return {"references": references}

    raise ValueError(
        "Policy save currently supports only policy_type values: "
        "'species_block', 'prompt', 'image_block', 'tone_profile', "
        "'descriptor_layer', 'registry'."
    )


def _parse_structured_object_from_raw(
    *,
    raw_content: str,
    policy_type: str,
) -> dict[str, object]:
    """Parse structured YAML/JSON raw content into one dictionary payload."""
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        try:
            parsed = yaml.safe_load(raw_content)
        except yaml.YAMLError as exc:  # pragma: no cover - exercised via ValueError branch
            raise ValueError(
                f"{policy_type} raw_content must be valid YAML/JSON object text."
            ) from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{policy_type} raw_content must be a YAML/JSON object.")
    return cast(dict[str, object], parsed)


def _extract_layer2_references(
    *,
    payload: dict[str, object],
    policy_type: str,
) -> list[dict[str, str]]:
    """Extract canonical Layer 2 ``references`` payload for descriptor/registry objects."""
    raw_references = payload.get("references")
    if raw_references is not None:
        return _normalize_reference_entries(references=raw_references, policy_type=policy_type)

    if policy_type == "registry":
        inferred_references = _infer_registry_references_from_legacy_payload(payload=payload)
        if inferred_references:
            return inferred_references
        raise ValueError(
            "registry content must include references, or legacy entries/slots with "
            "block_path values that resolve to Layer 1 policy objects."
        )

    raise ValueError("descriptor_layer content must include a non-empty references list.")


def _normalize_reference_entries(
    *,
    references: object,
    policy_type: str,
) -> list[dict[str, str]]:
    """Validate/normalize explicit Layer 2 references into canonical list form."""
    if not isinstance(references, list) or len(references) == 0:
        raise ValueError(f"{policy_type} content.references must be a non-empty list.")

    normalized: list[dict[str, str]] = []
    for index, item in enumerate(references):
        if not isinstance(item, dict):
            raise ValueError(
                f"{policy_type} content.references[{index}] must be an object with "
                "'policy_id' and 'variant'."
            )
        policy_id = str(item.get("policy_id", "")).strip()
        variant = str(item.get("variant", "")).strip()
        if not policy_id:
            raise ValueError(f"{policy_type} content.references[{index}].policy_id is required.")
        if not variant:
            raise ValueError(f"{policy_type} content.references[{index}].variant is required.")
        normalized.append({"policy_id": policy_id, "variant": variant})
    return normalized


def _infer_registry_references_from_legacy_payload(
    *,
    payload: dict[str, object],
) -> list[dict[str, str]]:
    """Derive Layer 2 references from legacy registry payloads.

    Legacy registry files typically encode source links using ``block_path`` or
    ``fragment_path`` fields. For migration, this helper extracts only paths
    that can be deterministically mapped to known Layer 1 policy object IDs.
    """
    candidates: list[str] = []
    entries = payload.get("entries")
    if isinstance(entries, list):
        candidates.extend(_collect_path_fields_from_entries(entries))

    slots = payload.get("slots")
    if isinstance(slots, dict):
        for slot_rows in slots.values():
            if isinstance(slot_rows, list):
                candidates.extend(_collect_path_fields_from_entries(slot_rows))

    resolved: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        reference = _policy_reference_from_legacy_path(candidate)
        if reference is None:
            continue
        identity = (reference["policy_id"], reference["variant"])
        if identity in seen:
            continue
        seen.add(identity)
        resolved.append(reference)
    return resolved


def _collect_path_fields_from_entries(entries: list[object]) -> list[str]:
    """Return recognized legacy path fields from a list of registry rows."""
    values: list[str] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        for key in ("block_path", "fragment_path", "prompt_path", "tone_profile_path"):
            raw_value = item.get(key)
            if isinstance(raw_value, str) and raw_value.strip():
                values.append(raw_value.strip())
    return values


def _policy_reference_from_legacy_path(path_value: str) -> dict[str, str] | None:
    """Map one legacy file path into canonical Layer 1 ``policy_id`` + variant."""
    normalized = path_value.replace("\\", "/").strip().lstrip("./")

    species_match = _LEGACY_SPECIES_BLOCK_PATH_PATTERN.fullmatch(normalized)
    if species_match is not None:
        return {
            "policy_id": f"species_block:image.blocks.species:{species_match.group('policy_key')}",
            "variant": species_match.group("variant"),
        }

    prompt_match = _LEGACY_PROMPT_PATH_PATTERN.fullmatch(normalized)
    if prompt_match is not None:
        namespace = prompt_match.group("namespace_path").replace("/", ".")
        return {
            "policy_id": f"prompt:{namespace}:{prompt_match.group('policy_key')}",
            "variant": prompt_match.group("variant"),
        }

    tone_match = _LEGACY_TONE_PROFILE_PATH_PATTERN.fullmatch(normalized)
    if tone_match is not None:
        return {
            "policy_id": f"tone_profile:image.tone_profiles:{tone_match.group('policy_key')}",
            "variant": tone_match.group("variant"),
        }

    return None


def _request_json(
    *,
    method: str,
    url: str,
    timeout_seconds: float,
    json_payload: dict[str, object | None] | None = None,
    allow_not_found: bool = False,
) -> dict[str, object] | None:
    """Issue one HTTP request and decode JSON response with stable errors."""
    # Wrapper preserved so existing call sites/tests keep using the legacy
    # helper name while transport behavior is centralized in one module.
    return mud_api_client.request_json(
        method=method,
        url=url,
        timeout_seconds=timeout_seconds,
        json_payload=cast(dict[str, object] | None, json_payload),
        allow_not_found=allow_not_found,
        error_prefix="Mud policy API request failed",
        non_object_error_message=(
            f"Mud policy API response for {method} {url} was not a JSON object."
        ),
        opener=urlopen,
    )


def _http_error_detail(exc: object) -> str:
    """Extract best-effort detail text from HTTP error responses."""
    return mud_api_client.mud_api_http_error_detail(exc)
