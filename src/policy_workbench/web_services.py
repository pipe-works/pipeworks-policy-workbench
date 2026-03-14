"""Service-layer helpers for the Phase 3 policy workbench web app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from pipeworks_ipc.hashing import compute_payload_hash as _compute_payload_hash

from . import (
    mud_api_client,
    web_diagnostics_services,
    web_local_policy_metadata,
    web_policy_proxy_services,
    web_runtime_services,
    web_source_services,
)
from .models import PolicyTreeSnapshot
from .mud_api_runtime import MudApiRuntimeConfig, resolve_mud_api_runtime_config
from .policy_authoring import selector_from_relative_path
from .web_models import (
    HashCanonicalResponse,
    PolicyActivationScopeResponse,
    PolicyInventoryResponse,
    PolicyObjectDetailResponse,
    PolicyPublishRunProxyResponse,
    PolicyTreeResponse,
    PolicyTypeOptionsResponse,
    RuntimeAuthResponse,
    RuntimeLoginResponse,
    ValidationResponse,
)

_EDITOR_FILE_SUFFIXES = {".txt", ".yaml", ".yml", ".json"}
_HASH_VERSION = "policy_tree_hash_v1"
_DEFAULT_CANONICAL_HASH_URL = "http://127.0.0.1:8000/api/policy/hash-snapshot"
_CANONICAL_HASH_URL_ENV = "PW_POLICY_HASH_SNAPSHOT_URL"
_DEFAULT_MUD_API_BASE_URL = "http://127.0.0.1:8000"
_MUD_API_BASE_URL_ENV = "PW_POLICY_MUD_API_BASE_URL"
_MUD_API_SESSION_ID_ENV = "PW_POLICY_MUD_SESSION_ID"
_LOCAL_POLICY_TYPES_FILE_ENV = "PW_POLICY_LOCAL_POLICY_TYPES_FILE"
_POLICY_API_ROLE_REQUIRED_DETAIL = "Policy API requires admin or superuser role."
_POLICY_ALLOWED_ROLES = {"admin", "superuser"}
_FALLBACK_POLICY_TYPES = (
    "species_block",
    "descriptor_layer",
    "registry",
    "prompt",
    "tone_profile",
)
_FALLBACK_POLICY_STATUSES = (
    "draft",
    "candidate",
    "active",
    "archived",
)

# Backward-compatible module export: existing tests and downstream callers patch
# ``web_services.compute_payload_hash`` directly.
compute_payload_hash = _compute_payload_hash

# IPC hashing remains intentionally even after removing the Sync Impact UI.
#
# Rationale:
# 1. Policy Workbench still needs deterministic, cross-repo-stable hashing
#    semantics for canonical policy payload processing and integrity helpers.
# 2. Mud-server and other pipe-works tools already use pipeworks_ipc as the
#    shared provenance contract; keeping this dependency prevents hash drift
#    between tools as policy workflows are tightened around API-only authoring.
# 3. The plain `compute_payload_hash` fallback path is preserved so local dev
#    still behaves deterministically if optional IPC helper symbols are absent.
try:
    import pipeworks_ipc.hashing as ipc_hashing
except ImportError:  # pragma: no cover - import path is expected in normal runtime
    ipc_hashing = None


@dataclass(frozen=True, slots=True)
class _PolicyHashEntry:
    """One normalized local policy file entry used for hash calculations."""

    relative_path: str
    content_hash: str


# Keep private alias for test/backward compatibility while shared resolver is
# adopted across modules.
_MudApiRuntimeConfig = MudApiRuntimeConfig


def resolve_source_root_for_web(
    *,
    root_override: str | None,
    map_path_override: str | None,
) -> Path:
    """Resolve canonical source root for web APIs."""
    return web_source_services.resolve_source_root_for_web(
        root_override=root_override,
        map_path_override=map_path_override,
    )


def build_tree_payload(source_root: Path) -> PolicyTreeResponse:
    """Build serialized tree-browser payload for the web UI."""
    return web_source_services.build_tree_payload(
        source_root,
        is_supported_editor_file=_is_supported_editor_file,
        selector_from_relative_path_fn=selector_from_relative_path,
    )


def build_runtime_auth_payload(
    *,
    mode_key: str,
    source_kind: str,
    active_server_url: str | None,
    session_id_override: str | None,
    base_url_override: str | None = None,
) -> RuntimeAuthResponse:
    """Build runtime auth/capability payload for server-backed policy operations.

    Policy APIs on mud-server are already restricted to admin/superuser roles.
    This probe gives the workbench a single explicit auth state so the UI can
    disable server-backed actions when the configured session is missing,
    expired, or lacks required role permissions.
    """

    return web_runtime_services.build_runtime_auth_payload(
        mode_key=mode_key,
        source_kind=source_kind,
        active_server_url=active_server_url,
        session_id_override=session_id_override,
        base_url_override=base_url_override,
        resolve_runtime_config=_resolve_mud_api_runtime_config,
        fetch_policy_capabilities=_fetch_policy_capabilities_payload,
        classify_runtime_probe_error=_classify_runtime_auth_probe_error,
    )


def build_runtime_login_payload(
    *,
    mode_key: str,
    source_kind: str,
    active_server_url: str | None,
    username: str,
    password: str,
    base_url_override: str | None = None,
) -> RuntimeLoginResponse:
    """Authenticate against the active mud-server URL and return session details."""
    return web_runtime_services.build_runtime_login_payload(
        mode_key=mode_key,
        source_kind=source_kind,
        active_server_url=active_server_url,
        username=username,
        password=password,
        base_url_override=base_url_override,
        default_base_url=_DEFAULT_MUD_API_BASE_URL,
        allowed_roles=_POLICY_ALLOWED_ROLES,
        normalize_base_url=_normalize_base_url,
        fetch_mud_api_json_anonymous=_fetch_mud_api_json_anonymous,
    )


def build_policy_type_options_payload(
    *,
    source_kind: str,
    active_server_url: str | None,
    session_id_override: str | None,
    base_url_override: str | None = None,
) -> PolicyTypeOptionsResponse:
    """Return canonical policy-type options sourced from mud-server capabilities."""
    return web_runtime_services.build_policy_type_options_payload(
        source_kind=source_kind,
        active_server_url=active_server_url,
        session_id_override=session_id_override,
        base_url_override=base_url_override,
        resolve_runtime_config=_resolve_mud_api_runtime_config,
        fetch_policy_capabilities=_fetch_policy_capabilities_payload,
    )


def build_policy_namespace_options_payload(
    *,
    source_kind: str,
    active_server_url: str | None,
    session_id_override: str | None,
    policy_type: str | None,
    base_url_override: str | None = None,
) -> PolicyTypeOptionsResponse:
    """Return canonical policy namespace options sourced from mud-server inventory."""
    return web_runtime_services.build_policy_namespace_options_payload(
        source_kind=source_kind,
        active_server_url=active_server_url,
        session_id_override=session_id_override,
        policy_type=policy_type,
        base_url_override=base_url_override,
        resolve_runtime_config=_resolve_mud_api_runtime_config,
        fetch_mud_api_json=_fetch_mud_api_json,
    )


def build_policy_status_options_payload(
    *,
    source_kind: str,
    active_server_url: str | None,
    session_id_override: str | None,
    base_url_override: str | None = None,
) -> PolicyTypeOptionsResponse:
    """Return canonical policy status options sourced from mud-server capabilities."""
    return web_runtime_services.build_policy_status_options_payload(
        source_kind=source_kind,
        active_server_url=active_server_url,
        session_id_override=session_id_override,
        base_url_override=base_url_override,
        resolve_runtime_config=_resolve_mud_api_runtime_config,
        fetch_policy_capabilities=_fetch_policy_capabilities_payload,
    )


def build_policy_inventory_payload(
    *,
    policy_type: str | None,
    namespace: str | None,
    status: str | None,
    session_id_override: str | None,
    base_url_override: str | None = None,
) -> PolicyInventoryResponse:
    """Build API-first policy inventory payload from mud-server canonical API."""
    return web_policy_proxy_services.build_policy_inventory_payload(
        policy_type=policy_type,
        namespace=namespace,
        status=status,
        session_id_override=session_id_override,
        base_url_override=base_url_override,
        resolve_runtime_config=_resolve_mud_api_runtime_config,
        fetch_mud_api_json=_fetch_mud_api_json,
    )


def build_policy_object_detail_payload(
    *,
    policy_id: str,
    variant: str | None,
    session_id_override: str | None,
    base_url_override: str | None = None,
) -> PolicyObjectDetailResponse:
    """Build API-first detail payload for one policy object variant."""
    return web_policy_proxy_services.build_policy_object_detail_payload(
        policy_id=policy_id,
        variant=variant,
        session_id_override=session_id_override,
        base_url_override=base_url_override,
        resolve_runtime_config=_resolve_mud_api_runtime_config,
        fetch_mud_api_json=_fetch_mud_api_json,
    )


def build_policy_activation_scope_payload(
    *,
    scope: str,
    effective: bool,
    session_id_override: str | None,
    base_url_override: str | None = None,
) -> PolicyActivationScopeResponse:
    """Build activation-scope payload from mud-server policy activation API."""
    return web_policy_proxy_services.build_policy_activation_scope_payload(
        scope=scope,
        effective=effective,
        session_id_override=session_id_override,
        base_url_override=base_url_override,
        resolve_runtime_config=_resolve_mud_api_runtime_config,
        fetch_mud_api_json=_fetch_mud_api_json,
    )


def build_policy_publish_run_payload(
    *,
    publish_run_id: int,
    session_id_override: str | None,
    base_url_override: str | None = None,
) -> PolicyPublishRunProxyResponse:
    """Build publish-run payload proxy from mud-server canonical publish API."""
    return web_policy_proxy_services.build_policy_publish_run_payload(
        publish_run_id=publish_run_id,
        session_id_override=session_id_override,
        base_url_override=base_url_override,
        resolve_runtime_config=_resolve_mud_api_runtime_config,
        fetch_mud_api_json=_fetch_mud_api_json,
    )


def read_policy_file(source_root: Path, relative_path: str) -> str:
    """Read one policy file by relative path with traversal protection."""
    return web_source_services.read_policy_file(
        source_root,
        relative_path,
        validate_supported_editor_path=_validate_supported_editor_path,
        resolve_file_under_root=_resolve_file_under_root,
    )


def build_validation_payload(source_root: Path) -> ValidationResponse:
    """Build serialized validation payload for right-panel reporting."""
    return web_source_services.build_validation_payload(
        source_root,
        filter_snapshot_to_supported_files=_filter_snapshot_to_supported_files,
    )


def _classify_runtime_auth_probe_error(error_detail: str) -> tuple[str, str]:
    """Classify mud-server capability probe failure into stable UI-facing status."""
    return web_runtime_services.classify_runtime_auth_probe_error(
        error_detail=error_detail,
        role_required_detail=_POLICY_API_ROLE_REQUIRED_DETAIL,
    )


def _fetch_policy_capabilities_payload(*, runtime: _MudApiRuntimeConfig) -> dict[str, object]:
    """Fetch mud-server policy capabilities for authorized sessions.

    The workbench uses this endpoint as the canonical contract for
    auth/capability checks and policy type/status option discovery.
    """
    return web_runtime_services.fetch_policy_capabilities_payload(
        runtime=runtime,
        fetch_mud_api_json=_fetch_mud_api_json,
    )


def _resolve_mud_api_runtime_config(
    *,
    session_id_override: str | None,
    base_url_override: str | None = None,
) -> _MudApiRuntimeConfig:
    """Resolve mud-server API runtime config from env vars and optional session override."""
    return resolve_mud_api_runtime_config(
        session_id_override=session_id_override,
        base_url_override=base_url_override,
        base_url_env_var=_MUD_API_BASE_URL_ENV,
        session_id_env_var=_MUD_API_SESSION_ID_ENV,
        default_base_url=_DEFAULT_MUD_API_BASE_URL,
        empty_base_url_error="Mud API base URL must not be empty.",
        missing_session_error="Mud API session id is required (PW_POLICY_MUD_SESSION_ID).",
    )


def _normalize_base_url(value: str | None) -> str:
    """Normalize mud API base URL and reject empty/invalid values."""
    return mud_api_client.normalize_base_url(value)


def _extract_string_list_from_capabilities_payload(
    *,
    payload: dict[str, object],
    field_name: str,
) -> list[str]:
    """Extract and normalize one string-list field from capabilities payload."""
    return web_runtime_services.extract_string_list_from_capabilities_payload(
        payload=payload,
        field_name=field_name,
    )


def _extract_namespaces_from_inventory_payload(payload: dict[str, object]) -> list[str]:
    """Extract stable namespace list from ``GET /api/policies`` payload."""
    return web_runtime_services.extract_namespaces_from_inventory_payload(payload)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    """Normalize duplicate-prone lists while preserving first-seen ordering."""
    return web_runtime_services.dedupe_preserve_order(values)


def _load_local_policy_types_from_disk() -> tuple[list[str], str, str | None]:
    """Load canonical policy types from local mud-server source file when available."""
    return web_local_policy_metadata.load_local_policy_types_from_disk(
        fallback_policy_types=_FALLBACK_POLICY_TYPES,
        resolve_source_path=_resolve_local_policy_types_source_path,
        load_constant_set_values=_load_local_constant_set_values,
        dedupe_preserve_order=_dedupe_preserve_order,
    )


def _load_local_policy_statuses_from_disk() -> tuple[list[str], str, str | None]:
    """Load canonical policy statuses from local mud-server source file."""
    return web_local_policy_metadata.load_local_policy_statuses_from_disk(
        fallback_policy_statuses=_FALLBACK_POLICY_STATUSES,
        resolve_source_path=_resolve_local_policy_types_source_path,
        load_constant_set_values=_load_local_constant_set_values,
        dedupe_preserve_order=_dedupe_preserve_order,
    )


def _resolve_local_policy_types_source_path() -> Path | None:
    """Resolve local canonical policy-type source file path."""
    return web_local_policy_metadata.resolve_local_policy_types_source_path(
        local_policy_types_file_env=_LOCAL_POLICY_TYPES_FILE_ENV,
    )


def _load_local_namespaces_from_disk(*, source_root: Path, policy_type: str | None) -> list[str]:
    """Derive canonical namespace options from local authorable policy files."""
    return web_local_policy_metadata.load_local_namespaces_from_disk(
        source_root=source_root,
        policy_type=policy_type,
        is_supported_editor_file=_is_supported_editor_file,
        selector_from_relative_path=selector_from_relative_path,
        dedupe_preserve_order=_dedupe_preserve_order,
    )


def _load_local_constant_set_values(*, source_path: Path, constant_name: str) -> list[str] | None:
    """Load one module-level set constant list from a Python source file."""
    return web_local_policy_metadata.load_local_constant_set_values(
        source_path=source_path,
        constant_name=constant_name,
    )


def _fetch_mud_api_json(
    *,
    runtime: _MudApiRuntimeConfig,
    method: str,
    path: str,
    query_params: dict[str, str],
) -> dict[str, object]:
    """Issue one mud-server API request and return parsed JSON object payload."""
    # Wrapper preserved for backward compatibility while the shared transport
    # implementation is adopted across service modules.
    return mud_api_client.fetch_mud_api_json(
        runtime=runtime,
        method=method,
        path=path,
        query_params=query_params,
        opener=urlopen,
    )


def _fetch_mud_api_json_anonymous(
    *,
    base_url: str,
    method: str,
    path: str,
    body: dict[str, object] | None,
    timeout_seconds: float = 8.0,
) -> dict[str, object]:
    """Issue one mud-server API request without session query injection."""
    # Wrapper preserved for backward compatibility while the shared transport
    # implementation is adopted across service modules.
    return mud_api_client.fetch_mud_api_json_anonymous(
        base_url=base_url,
        method=method,
        path=path,
        body=body,
        timeout_seconds=timeout_seconds,
        opener=urlopen,
    )


def _mud_api_http_error_detail(exc: HTTPError) -> str:
    """Extract best-effort detail from mud-server API HTTP error payloads."""
    return mud_api_client.mud_api_http_error_detail(exc)


def _resolve_canonical_hash_snapshot_url(url_override: str | None) -> str:
    """Resolve canonical hash snapshot URL from override, env var, or default."""
    return web_diagnostics_services.resolve_canonical_hash_snapshot_url(
        url_override,
        canonical_hash_url_env=_CANONICAL_HASH_URL_ENV,
        default_canonical_hash_url=_DEFAULT_CANONICAL_HASH_URL,
    )


def _fetch_canonical_hash_snapshot(url: str) -> HashCanonicalResponse:
    """Fetch and validate canonical mud-server hash snapshot payload."""
    return web_diagnostics_services.fetch_canonical_hash_snapshot(
        url,
        opener=urlopen,
        response_model=HashCanonicalResponse,
    )


def _compute_file_hash(relative_path: str, content_bytes: bytes) -> str:
    """Compute deterministic policy file hash using IPC as the primary contract.

    Even with Sync Impact removed from the web UI, this helper stays because
    deterministic hash identity is part of the cross-tool policy provenance
    contract. The IPC implementation is authoritative when available; the local
    fallback keeps behavior stable in constrained environments.
    """

    return web_diagnostics_services.compute_file_hash(
        relative_path,
        content_bytes,
        ipc_hashing_module=ipc_hashing,
        hash_version=_HASH_VERSION,
    )


def _compute_tree_hash(entries: list[_PolicyHashEntry]) -> str:
    """Compute deterministic policy tree hash using IPC as the primary contract.

    This helper remains to keep tree-level hash semantics aligned with mud-server
    and other clients that rely on pipeworks_ipc for deterministic provenance.
    A payload-hash fallback remains for robust local execution.
    """

    diagnostics_entries = [
        web_diagnostics_services.PolicyHashEntry(
            relative_path=entry.relative_path,
            content_hash=entry.content_hash,
        )
        for entry in entries
    ]
    return web_diagnostics_services.compute_tree_hash(
        entries=diagnostics_entries,
        ipc_hashing_module=ipc_hashing,
        hash_version=_HASH_VERSION,
    )


def _normalize_relative_path(relative_path: str) -> str:
    """Normalize a policy-relative path and reject traversal-like values."""
    return web_diagnostics_services.normalize_relative_path(relative_path)


def _resolve_file_under_root(source_root: Path, relative_path: str) -> Path:
    """Resolve a file path safely under ``source_root``.

    Raises ``ValueError`` when the resolved path escapes source_root.
    """
    return web_source_services.resolve_file_under_root(source_root, relative_path)


def _is_supported_editor_file(relative_path: str) -> bool:
    """Return whether ``relative_path`` should be visible/editable in the web editor."""
    return web_diagnostics_services.is_supported_editor_file(
        relative_path,
        editor_file_suffixes=_EDITOR_FILE_SUFFIXES,
    )


def _validate_supported_editor_path(relative_path: str) -> None:
    """Raise ``ValueError`` when web editor is asked to read/write unsupported files."""
    web_diagnostics_services.validate_supported_editor_path(
        relative_path,
        editor_file_suffixes=_EDITOR_FILE_SUFFIXES,
    )


def _filter_snapshot_to_supported_files(snapshot: PolicyTreeSnapshot) -> PolicyTreeSnapshot:
    """Return snapshot narrowed to files supported by the web workbench editor."""
    return web_diagnostics_services.filter_snapshot_to_supported_files(
        snapshot,
        editor_file_suffixes=_EDITOR_FILE_SUFFIXES,
    )


def _read_optional_text(path: Path | None) -> str | None:
    """Read UTF-8 text from ``path`` when available, otherwise return ``None``."""
    return web_diagnostics_services.read_optional_text(path)


def _content_signature(*, source_content: str | None, exists: bool) -> str:
    """Build deterministic content signature used for grouping variants."""
    return web_diagnostics_services.content_signature(
        source_content=source_content,
        exists=exists,
    )


def _canonical_source_label(source_root: Path) -> str:
    """Build human-readable source column label for compare modal."""
    return web_diagnostics_services.canonical_source_label(source_root)
