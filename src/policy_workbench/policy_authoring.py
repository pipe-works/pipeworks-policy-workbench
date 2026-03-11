"""Policy-object authoring helpers for Phase 2 API-only workflows.

This module is the bridge between workbench editing and mud-server canonical
policy APIs. It provides:
- deterministic mapping from canonical relative paths to policy selectors
- mud-server request orchestration for validate -> save -> optional activate
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .extractors import extract_yaml_text_field

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


def resolve_runtime_config(*, session_id_override: str | None = None) -> MudPolicyRuntimeConfig:
    """Resolve mud-server API runtime config from env and optional overrides."""
    base_url = os.getenv(_MUD_API_BASE_URL_ENV, _DEFAULT_MUD_API_BASE_URL).strip().rstrip("/")
    if not base_url:
        raise ValueError("Mud policy API base URL must not be empty.")

    session_id_candidate = (
        session_id_override
        if session_id_override is not None
        else os.getenv(_MUD_API_SESSION_ID_ENV, "")
    )
    session_id = (session_id_candidate or "").strip()
    if not session_id:
        raise ValueError(
            "Mud policy session id is required. Set PW_POLICY_MUD_SESSION_ID or pass session_id."
        )

    return MudPolicyRuntimeConfig(base_url=base_url, session_id=session_id)


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

    if selector.policy_type == "tone_profile":
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ValueError("tone_profile raw_content must be valid JSON object text.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("tone_profile raw_content must be a JSON object.")
        return cast(dict[str, object], parsed)

    raise ValueError(
        "Policy save currently supports only policy_type values: "
        "'species_block', 'prompt', 'tone_profile'."
    )


def _request_json(
    *,
    method: str,
    url: str,
    timeout_seconds: float,
    json_payload: dict[str, object | None] | None = None,
    allow_not_found: bool = False,
) -> dict[str, object] | None:
    """Issue one HTTP request and decode JSON response with stable errors."""
    body = None
    headers = {"Accept": "application/json"}
    if json_payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(json_payload).encode("utf-8")

    request = Request(url=url, method=method, data=body, headers=headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            parsed = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if allow_not_found and exc.code == 404:
            return None
        detail = _http_error_detail(exc)
        raise ValueError(f"Mud policy API request failed ({method} {url}): {detail}") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Mud policy API request failed ({method} {url}): {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Mud policy API response for {method} {url} was not a JSON object.")
    return parsed


def _http_error_detail(exc: HTTPError) -> str:
    """Extract best-effort detail text from HTTP error responses."""
    default_detail = f"HTTP {exc.code}"
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_detail
    if isinstance(payload, dict):
        detail = payload.get("detail")
        code = payload.get("code")
        if detail and code:
            return f"{code}: {detail}"
        if detail:
            return str(detail)
    return default_detail
