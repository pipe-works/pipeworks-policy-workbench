"""Service-layer helpers for the Phase 3 policy workbench web app."""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pipeworks_ipc.hashing import compute_payload_hash

from . import mud_api_client, web_runtime_services
from .mirror_map import load_mirror_map, resolve_mirror_map_path
from .models import IssueLevel, PolicyTreeSnapshot
from .mud_api_runtime import MudApiRuntimeConfig, resolve_mud_api_runtime_config
from .pathing import resolve_policy_root
from .policy_authoring import selector_from_relative_path
from .sync_models import SyncAction, SyncActionType, SyncPlan
from .sync_planner import build_sync_plan
from .tree_model import build_policy_tree_snapshot
from .validators import validate_snapshot
from .web_models import (
    HashCanonicalResponse,
    HashStatusResponse,
    HashTargetStatusResponse,
    PolicyActivationScopeResponse,
    PolicyArtifactResponse,
    PolicyInventoryResponse,
    PolicyObjectDetailResponse,
    PolicyObjectSummaryResponse,
    PolicyPublishRunProxyResponse,
    PolicyTreeResponse,
    PolicyTypeOptionsResponse,
    RuntimeAuthResponse,
    RuntimeLoginResponse,
    SyncActionResponse,
    SyncCompareResponse,
    SyncCompareVariantResponse,
    SyncPlanResponse,
    ValidationIssueResponse,
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
    """Resolve canonical source root for web APIs.

    Resolution precedence:
    1. Explicit ``root_override``
    2. ``source.root`` in mirror-map config
    3. Default pathing resolution from ``resolve_policy_root``
    """

    if root_override:
        return resolve_policy_root(explicit_root=root_override)

    resolved_map_path = resolve_mirror_map_path(explicit_map_path=map_path_override)
    mirror_map = load_mirror_map(resolved_map_path)
    if mirror_map.source_root is not None:
        return mirror_map.source_root

    return resolve_policy_root(explicit_root=None)


def build_tree_payload(source_root: Path) -> PolicyTreeResponse:
    """Build serialized tree-browser payload for the web UI."""

    snapshot = build_policy_tree_snapshot(source_root)
    artifacts: list[PolicyArtifactResponse] = []
    for artifact in snapshot.artifacts:
        if not _is_supported_editor_file(artifact.relative_path):
            continue
        selector = selector_from_relative_path(artifact.relative_path)
        artifacts.append(
            PolicyArtifactResponse(
                relative_path=artifact.relative_path,
                role=artifact.role.value,
                has_prompt_text=bool((artifact.prompt_text or "").strip()),
                policy_type=selector.policy_type if selector else None,
                namespace=selector.namespace if selector else None,
                policy_key=selector.policy_key if selector else None,
                variant=selector.variant if selector else None,
                is_authorable=selector is not None,
            )
        )

    # The tree sidebar is intentionally scoped to editable policy files only.
    directory_set = {"policies"}
    for artifact_response in artifacts:
        parent = Path(artifact_response.relative_path).parent.as_posix()
        if parent and parent != ".":
            directory_set.add(parent)

    return PolicyTreeResponse(
        source_root=str(snapshot.root),
        directories=sorted(directory_set),
        artifacts=artifacts,
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
    runtime = _resolve_mud_api_runtime_config(
        session_id_override=session_id_override,
        base_url_override=base_url_override,
    )

    query_params: dict[str, str] = {}
    if (policy_type or "").strip():
        query_params["policy_type"] = str(policy_type).strip()
    if (namespace or "").strip():
        query_params["namespace"] = str(namespace).strip()
    if (status or "").strip():
        query_params["status"] = str(status).strip()

    payload = _fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path="/api/policies",
        query_params=query_params,
    )
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Mud policy inventory payload must include 'items' list.")

    items: list[PolicyObjectSummaryResponse] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("Mud policy inventory items must be JSON objects.")
        detail = PolicyObjectDetailResponse.model_validate(raw_item)
        items.append(
            PolicyObjectSummaryResponse(
                policy_id=detail.policy_id,
                policy_type=detail.policy_type,
                namespace=detail.namespace,
                policy_key=detail.policy_key,
                variant=detail.variant,
                schema_version=detail.schema_version,
                policy_version=detail.policy_version,
                status=detail.status,
                content_hash=detail.content_hash,
                updated_at=detail.updated_at,
                updated_by=detail.updated_by,
            )
        )

    return PolicyInventoryResponse(
        filters={
            "policy_type": query_params.get("policy_type"),
            "namespace": query_params.get("namespace"),
            "status": query_params.get("status"),
        },
        item_count=len(items),
        items=items,
    )


def build_policy_object_detail_payload(
    *,
    policy_id: str,
    variant: str | None,
    session_id_override: str | None,
    base_url_override: str | None = None,
) -> PolicyObjectDetailResponse:
    """Build API-first detail payload for one policy object variant."""
    runtime = _resolve_mud_api_runtime_config(
        session_id_override=session_id_override,
        base_url_override=base_url_override,
    )
    query_params: dict[str, str] = {}
    if (variant or "").strip():
        query_params["variant"] = str(variant).strip()

    payload = _fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path=f"/api/policies/{quote(policy_id, safe='')}",
        query_params=query_params,
    )
    return cast(PolicyObjectDetailResponse, PolicyObjectDetailResponse.model_validate(payload))


def build_policy_activation_scope_payload(
    *,
    scope: str,
    effective: bool,
    session_id_override: str | None,
    base_url_override: str | None = None,
) -> PolicyActivationScopeResponse:
    """Build activation-scope payload from mud-server policy activation API."""
    runtime = _resolve_mud_api_runtime_config(
        session_id_override=session_id_override,
        base_url_override=base_url_override,
    )
    payload = _fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path="/api/policy-activations",
        query_params={
            "scope": scope,
            "effective": "true" if effective else "false",
        },
    )
    return cast(
        PolicyActivationScopeResponse,
        PolicyActivationScopeResponse.model_validate(payload),
    )


def build_policy_publish_run_payload(
    *,
    publish_run_id: int,
    session_id_override: str | None,
    base_url_override: str | None = None,
) -> PolicyPublishRunProxyResponse:
    """Build publish-run payload proxy from mud-server canonical publish API."""
    runtime = _resolve_mud_api_runtime_config(
        session_id_override=session_id_override,
        base_url_override=base_url_override,
    )
    payload = _fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path=f"/api/policy-publish/{publish_run_id}",
        query_params={},
    )
    return cast(
        PolicyPublishRunProxyResponse,
        PolicyPublishRunProxyResponse.model_validate(payload),
    )


def read_policy_file(source_root: Path, relative_path: str) -> str:
    """Read one policy file by relative path with traversal protection."""

    _validate_supported_editor_path(relative_path)
    file_path = _resolve_file_under_root(source_root=source_root, relative_path=relative_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Policy file not found: {relative_path}")
    if not file_path.is_file():
        raise IsADirectoryError(f"Policy path is not a file: {relative_path}")

    return file_path.read_text(encoding="utf-8")


def write_policy_file(source_root: Path, relative_path: str, content: str) -> int:
    """Write one policy file under source root and return bytes written."""

    _validate_supported_editor_path(relative_path)
    file_path = _resolve_file_under_root(source_root=source_root, relative_path=relative_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return len(content.encode("utf-8"))


def build_validation_payload(source_root: Path) -> ValidationResponse:
    """Build serialized validation payload for right-panel reporting."""

    snapshot = build_policy_tree_snapshot(source_root)
    report = validate_snapshot(_filter_snapshot_to_supported_files(snapshot))

    issues = [
        ValidationIssueResponse(
            level=issue.level.value,
            code=issue.code,
            message=issue.message,
            relative_path=issue.relative_path,
        )
        for issue in report.issues
    ]

    counts = {
        IssueLevel.ERROR.value: report.count(IssueLevel.ERROR),
        IssueLevel.WARNING.value: report.count(IssueLevel.WARNING),
        IssueLevel.INFO.value: report.count(IssueLevel.INFO),
    }

    return ValidationResponse(source_root=str(report.root), counts=counts, issues=issues)


def build_sync_payload(
    *,
    source_root: Path,
    map_path_override: str | None,
    include_unchanged: bool,
) -> SyncPlanResponse:
    """Build serialized sync-plan payload for impact visualization."""

    mirror_map_path = resolve_mirror_map_path(explicit_map_path=map_path_override)
    mirror_map = load_mirror_map(mirror_map_path)
    plan = _filter_sync_plan_to_supported_files(
        build_sync_plan(source_root=source_root, mirror_map=mirror_map)
    )

    actions = [
        _serialize_action(action)
        for action in plan.actions
        if include_unchanged or action.action != SyncActionType.UNCHANGED
    ]

    return SyncPlanResponse(
        source_root=str(plan.source_root),
        map_path=str(plan.map_path),
        counts=_counts_for_plan(plan),
        actions=actions,
    )


def build_sync_plan_for_apply(
    *,
    source_root: Path,
    map_path_override: str | None,
) -> SyncPlan:
    """Build raw sync plan object for apply endpoint execution."""

    mirror_map_path = resolve_mirror_map_path(explicit_map_path=map_path_override)
    mirror_map = load_mirror_map(mirror_map_path)
    plan = build_sync_plan(source_root=source_root, mirror_map=mirror_map)
    return _filter_sync_plan_to_supported_files(plan)


def build_sync_compare_payload(
    *,
    source_root: Path,
    map_path_override: str | None,
    relative_path: str,
    focus_target: str | None = None,
) -> SyncCompareResponse:
    """Build side-by-side source/target comparison payload for one path."""

    _validate_supported_editor_path(relative_path)
    mirror_map_path = resolve_mirror_map_path(explicit_map_path=map_path_override)
    mirror_map = load_mirror_map(mirror_map_path)

    plan = _filter_sync_plan_to_supported_files(
        build_sync_plan(source_root=source_root, mirror_map=mirror_map)
    )
    action_by_target = _action_by_target_for_relative_path(plan=plan, relative_path=relative_path)

    source_path = source_root / relative_path
    source_content = _read_optional_text(source_path)
    source_exists = source_path.exists() and source_path.is_file()
    source_signature = _content_signature(source_content=source_content, exists=source_exists)

    signatures_seen: dict[str, int] = {source_signature: 1}
    next_group_id = 2

    variants: list[SyncCompareVariantResponse] = [
        SyncCompareVariantResponse(
            label=_canonical_source_label(source_root),
            kind="source",
            target=None,
            action=None,
            path=str(source_path),
            exists=source_exists,
            matches_source=True,
            group_id=1,
            content=source_content,
        )
    ]

    targets_sorted = sorted(mirror_map.targets, key=lambda target: target.name)
    if focus_target:
        targets_sorted.sort(key=lambda target: (target.name != focus_target, target.name))

    for target in targets_sorted:
        target_path = target.root / relative_path
        target_exists = target_path.exists() and target_path.is_file()
        target_content = _read_optional_text(target_path)
        signature = _content_signature(source_content=target_content, exists=target_exists)
        if signature not in signatures_seen:
            signatures_seen[signature] = next_group_id
            next_group_id += 1

        variants.append(
            SyncCompareVariantResponse(
                label=target.name,
                kind="target",
                target=target.name,
                action=action_by_target.get(target.name),
                path=str(target_path),
                exists=target_exists,
                matches_source=(signature == source_signature),
                group_id=signatures_seen[signature],
                content=target_content,
            )
        )

    return SyncCompareResponse(
        relative_path=relative_path,
        source_root=str(source_root),
        focus_target=focus_target,
        unique_variant_count=len(signatures_seen),
        variants=variants,
    )


def build_hash_status_payload(
    *,
    source_root: Path,
    map_path_override: str | None,
    canonical_snapshot_url_override: str | None = None,
) -> HashStatusResponse:
    """Build hash alignment status against canonical mud-server hash snapshot."""

    mirror_map_path = resolve_mirror_map_path(explicit_map_path=map_path_override)
    mirror_map = load_mirror_map(mirror_map_path)

    canonical_entries = _collect_local_policy_entries(source_root)
    canonical_by_path = {entry.relative_path: entry for entry in canonical_entries}
    canonical_paths = set(canonical_by_path.keys())
    canonical_snapshot: HashCanonicalResponse | None = None
    canonical_url: str | None = None
    canonical_error: str | None = None

    try:
        canonical_url = _resolve_canonical_hash_snapshot_url(canonical_snapshot_url_override)
        canonical_snapshot = _fetch_canonical_hash_snapshot(canonical_url)
    except ValueError as exc:
        canonical_snapshot = None
        canonical_error = str(exc)

    target_statuses: list[HashTargetStatusResponse] = []
    for target in sorted(mirror_map.targets, key=lambda current: current.name):
        target_entries = _collect_local_policy_entries(target.root)
        target_by_path = {entry.relative_path: entry for entry in target_entries}

        missing_count = 0
        different_count = 0
        projected_entries: list[_PolicyHashEntry] = []

        for relative_path in sorted(canonical_paths):
            source_entry = canonical_by_path[relative_path]
            target_entry = target_by_path.get(relative_path)
            if target_entry is None:
                missing_count += 1
                projected_entries.append(
                    _PolicyHashEntry(
                        relative_path=relative_path,
                        content_hash=_compute_missing_content_hash(relative_path),
                    )
                )
                continue

            projected_entries.append(target_entry)
            if target_entry.content_hash != source_entry.content_hash:
                different_count += 1

        target_only_count = sum(1 for path in target_by_path if path not in canonical_paths)
        target_root_hash = _compute_tree_hash(projected_entries)
        matches_canonical = (
            target_root_hash == canonical_snapshot.root_hash if canonical_snapshot else None
        )

        target_statuses.append(
            HashTargetStatusResponse(
                name=target.name,
                file_count=len(target_entries),
                root_hash=target_root_hash,
                matches_canonical=matches_canonical,
                missing_count=missing_count,
                different_count=different_count,
                target_only_count=target_only_count,
            )
        )

    if canonical_snapshot is None:
        status = "canonical_unavailable"
    else:
        status = "ok" if all(target.matches_canonical for target in target_statuses) else "drift"

    return HashStatusResponse(
        status=status,
        canonical=canonical_snapshot,
        canonical_url=canonical_url,
        canonical_error=canonical_error,
        targets=target_statuses,
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
    source_path = _resolve_local_policy_types_source_path()
    if source_path is None:
        return (
            list(_FALLBACK_POLICY_TYPES),
            "fallback",
            "Local mud-server canonical policy type source file was not found.",
        )

    values = _load_local_constant_set_values(
        source_path=source_path,
        constant_name="_SUPPORTED_POLICY_TYPES",
    )
    if values is None:
        return (
            list(_FALLBACK_POLICY_TYPES),
            "fallback",
            "Local policy type source file did not expose _SUPPORTED_POLICY_TYPES.",
        )

    parsed_policy_types = _dedupe_preserve_order(values)
    if not parsed_policy_types:
        return (
            list(_FALLBACK_POLICY_TYPES),
            "fallback",
            "Local policy type source file did not provide usable policy types.",
        )
    return (
        parsed_policy_types,
        "local_disk",
        f"Loaded canonical policy types from {source_path}.",
    )


def _load_local_policy_statuses_from_disk() -> tuple[list[str], str, str | None]:
    """Load canonical policy statuses from local mud-server source file."""
    source_path = _resolve_local_policy_types_source_path()
    if source_path is None:
        return (
            list(_FALLBACK_POLICY_STATUSES),
            "fallback",
            "Local mud-server canonical policy status source file was not found.",
        )

    values = _load_local_constant_set_values(
        source_path=source_path,
        constant_name="_SUPPORTED_STATUSES",
    )
    if values is None:
        return (
            list(_FALLBACK_POLICY_STATUSES),
            "fallback",
            "Local policy status source file did not expose _SUPPORTED_STATUSES.",
        )

    parsed_statuses = _dedupe_preserve_order(values)
    if not parsed_statuses:
        return (
            list(_FALLBACK_POLICY_STATUSES),
            "fallback",
            "Local policy status source file did not provide usable statuses.",
        )
    return (
        parsed_statuses,
        "local_disk",
        f"Loaded canonical policy statuses from {source_path}.",
    )


def _resolve_local_policy_types_source_path() -> Path | None:
    """Resolve local canonical policy-type source file path."""
    override = (os.getenv(_LOCAL_POLICY_TYPES_FILE_ENV, "") or "").strip()
    if override:
        return Path(override).expanduser()

    workspace_root = Path(__file__).resolve().parents[3]
    return (
        workspace_root
        / "pipeworks_mud_server"
        / "src"
        / "mud_server"
        / "services"
        / "policy_service.py"
    )


def _load_local_namespaces_from_disk(*, source_root: Path, policy_type: str | None) -> list[str]:
    """Derive canonical namespace options from local authorable policy files."""
    if not source_root.exists() or not source_root.is_dir():
        return []

    namespaces: list[str] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        try:
            relative_path = path.relative_to(source_root).as_posix()
        except ValueError:
            continue
        if not _is_supported_editor_file(relative_path):
            continue
        selector = selector_from_relative_path(relative_path)
        if selector is None:
            continue
        if policy_type and selector.policy_type != policy_type:
            continue
        namespaces.append(selector.namespace)
    return _dedupe_preserve_order(namespaces)


def _load_local_constant_set_values(*, source_path: Path, constant_name: str) -> list[str] | None:
    """Load one module-level set constant list from a Python source file."""
    if not source_path.exists():
        return None
    try:
        text = source_path.read_text(encoding="utf-8")
    except OSError:
        return None
    pattern = rf"{re.escape(constant_name)}\s*=\s*{{(?P<body>[^}}]*)}}"
    match = re.search(pattern, text, flags=re.DOTALL)
    if match is None:
        return None
    return re.findall(r"['\"]([^'\"]+)['\"]", match.group("body"))


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

    candidate = url_override or os.getenv(_CANONICAL_HASH_URL_ENV) or _DEFAULT_CANONICAL_HASH_URL
    normalized = (candidate or "").strip()
    if not normalized:
        raise ValueError("Canonical hash snapshot URL must not be empty")
    return normalized


def _fetch_canonical_hash_snapshot(url: str) -> HashCanonicalResponse:
    """Fetch and validate canonical mud-server hash snapshot payload."""

    request = Request(url=url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=5.0) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to fetch canonical hash snapshot from {url}: {exc}") from exc

    validated = HashCanonicalResponse.model_validate(payload)
    if not isinstance(validated, HashCanonicalResponse):
        raise ValueError(f"Canonical hash snapshot from {url} did not match expected schema")
    return validated


def _collect_local_policy_entries(policy_root: Path) -> list[_PolicyHashEntry]:
    """Collect deterministic policy file hash entries from ``policy_root``."""

    entries: list[_PolicyHashEntry] = []
    for path in sorted(policy_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _EDITOR_FILE_SUFFIXES:
            continue

        relative_path = _normalize_relative_path(path.relative_to(policy_root).as_posix())
        entries.append(
            _PolicyHashEntry(
                relative_path=relative_path,
                content_hash=_compute_file_hash(relative_path, path.read_bytes()),
            )
        )

    return entries


def _compute_file_hash(relative_path: str, content_bytes: bytes) -> str:
    """Compute deterministic policy file hash using IPC as the primary contract.

    Even with Sync Impact removed from the web UI, this helper stays because
    deterministic hash identity is part of the cross-tool policy provenance
    contract. The IPC implementation is authoritative when available; the local
    fallback keeps behavior stable in constrained environments.
    """

    helper = getattr(ipc_hashing, "compute_policy_file_hash", None) if ipc_hashing else None
    if callable(helper):
        return str(helper(relative_path, content_bytes))

    normalized_path = _normalize_relative_path(relative_path)
    return str(
        compute_payload_hash(
            {
                "hash_version": _HASH_VERSION,
                "relative_path": normalized_path,
                "content_bytes_hex": content_bytes.hex(),
            }
        )
    )


def _compute_tree_hash(entries: list[_PolicyHashEntry]) -> str:
    """Compute deterministic policy tree hash using IPC as the primary contract.

    This helper remains to keep tree-level hash semantics aligned with mud-server
    and other clients that rely on pipeworks_ipc for deterministic provenance.
    A payload-hash fallback remains for robust local execution.
    """

    helper = getattr(ipc_hashing, "compute_policy_tree_hash", None) if ipc_hashing else None
    entry_cls = getattr(ipc_hashing, "PolicyHashEntry", None) if ipc_hashing else None
    if callable(helper) and entry_cls is not None:
        ipc_entries = [
            entry_cls(relative_path=entry.relative_path, content_hash=entry.content_hash)
            for entry in entries
        ]
        return str(helper(ipc_entries))

    payload_entries = [
        {
            "relative_path": _normalize_relative_path(entry.relative_path),
            "content_hash": entry.content_hash,
        }
        for entry in entries
    ]
    payload_entries.sort(key=lambda item: str(item["relative_path"]))
    return str(compute_payload_hash({"hash_version": _HASH_VERSION, "entries": payload_entries}))


def _compute_missing_content_hash(relative_path: str) -> str:
    """Build deterministic hash marker for missing canonical-managed files."""

    normalized_path = _normalize_relative_path(relative_path)
    return str(
        compute_payload_hash(
            {
                "hash_version": _HASH_VERSION,
                "relative_path": normalized_path,
                "missing": True,
            }
        )
    )


def _normalize_relative_path(relative_path: str) -> str:
    """Normalize a policy-relative path and reject traversal-like values."""

    as_posix = PurePosixPath(relative_path.replace("\\", "/")).as_posix()
    if as_posix.startswith("../") or "/../" in f"/{as_posix}":
        raise ValueError(f"Policy relative path must not traverse upwards: {relative_path!r}")

    normalized = as_posix.lstrip("./")
    if normalized in {"", "."}:
        raise ValueError("Policy relative path must not be empty")
    return normalized


def _resolve_file_under_root(source_root: Path, relative_path: str) -> Path:
    """Resolve a file path safely under ``source_root``.

    Raises ``ValueError`` when the resolved path escapes source_root.
    """

    candidate = (source_root / relative_path).resolve()

    if source_root not in candidate.parents and candidate != source_root:
        raise ValueError(f"Relative path escapes source root: {relative_path}")

    return candidate


def _serialize_action(action: SyncAction) -> SyncActionResponse:
    """Convert planner action into JSON-serializable web response model."""

    return SyncActionResponse(
        target=action.target_name,
        relative_path=action.relative_path,
        action=action.action.value,
        source_path=str(action.source_path) if action.source_path else None,
        target_path=str(action.target_path) if action.target_path else None,
        reason=action.reason,
    )


def _counts_for_plan(plan: SyncPlan) -> dict[str, int]:
    """Count action types from a sync plan."""

    counts = Counter(action.action for action in plan.actions)
    return {
        SyncActionType.CREATE.value: counts[SyncActionType.CREATE],
        SyncActionType.UPDATE.value: counts[SyncActionType.UPDATE],
        SyncActionType.UNCHANGED.value: counts[SyncActionType.UNCHANGED],
        SyncActionType.TARGET_ONLY.value: counts[SyncActionType.TARGET_ONLY],
    }


def _is_supported_editor_file(relative_path: str) -> bool:
    """Return whether ``relative_path`` should be visible/editable in the web editor."""

    return Path(relative_path).suffix.lower() in _EDITOR_FILE_SUFFIXES


def _validate_supported_editor_path(relative_path: str) -> None:
    """Raise ``ValueError`` when web editor is asked to read/write unsupported files."""

    if not _is_supported_editor_file(relative_path):
        raise ValueError(
            "Only .txt, .yaml, .yml, and .json policy files are supported by the web editor"
        )


def _filter_snapshot_to_supported_files(snapshot: PolicyTreeSnapshot) -> PolicyTreeSnapshot:
    """Return snapshot narrowed to files supported by the web workbench editor."""

    supported_artifacts = [
        artifact
        for artifact in snapshot.artifacts
        if _is_supported_editor_file(artifact.relative_path)
    ]
    return PolicyTreeSnapshot(
        root=snapshot.root,
        directories=snapshot.directories,
        artifacts=supported_artifacts,
    )


def _filter_sync_plan_to_supported_files(plan: SyncPlan) -> SyncPlan:
    """Return sync plan narrowed to files supported by the web workbench editor."""

    supported_actions = [
        action for action in plan.actions if _is_supported_editor_file(action.relative_path)
    ]
    return SyncPlan(source_root=plan.source_root, map_path=plan.map_path, actions=supported_actions)


def _action_by_target_for_relative_path(plan: SyncPlan, *, relative_path: str) -> dict[str, str]:
    """Return sync action type value keyed by target name for one relative path."""

    actions: dict[str, str] = {}
    for action in plan.actions:
        if action.relative_path != relative_path:
            continue
        actions[action.target_name] = action.action.value
    return actions


def _read_optional_text(path: Path | None) -> str | None:
    """Read UTF-8 text from ``path`` when available, otherwise return ``None``."""

    if path is None:
        return None
    if not path.exists() or not path.is_file():
        return None

    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Unable to read text for diff: {path} ({exc})") from exc


def _content_signature(*, source_content: str | None, exists: bool) -> str:
    """Build deterministic content signature used for grouping variants."""

    if not exists:
        return "__missing__"
    if source_content is None:
        return "__unreadable__"
    return str(compute_payload_hash({"content": source_content}))


def _canonical_source_label(source_root: Path) -> str:
    """Build human-readable source column label for compare modal."""

    root_text = str(source_root).lower()
    if "pipeworks_mud_server" in root_text:
        return "canonical-source: mud-server"

    repo_name = source_root.parts[-3] if len(source_root.parts) >= 3 else source_root.name
    normalized = (
        repo_name.replace("pipeworks_", "").replace("pipeworks-", "").replace("_", "-").strip("-")
    )
    return f"canonical-source: {normalized or 'source'}"
