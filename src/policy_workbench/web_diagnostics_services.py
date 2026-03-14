"""Focused diagnostics/hash/sync service helpers for web routes.

This module isolates diagnostics-heavy behavior so ``web_services`` can remain
an orchestration layer while Phase 2 decomposition completes.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipeworks_ipc.hashing import compute_payload_hash

from .mirror_map import load_mirror_map, resolve_mirror_map_path
from .models import PolicyTreeSnapshot
from .sync_models import SyncAction, SyncActionType, SyncPlan
from .sync_planner import build_sync_plan
from .web_models import (
    HashCanonicalResponse,
    HashStatusResponse,
    HashTargetStatusResponse,
    SyncActionResponse,
    SyncCompareResponse,
    SyncCompareVariantResponse,
    SyncPlanResponse,
)

_EDITOR_FILE_SUFFIXES = {".txt", ".yaml", ".yml", ".json"}
_HASH_VERSION = "policy_tree_hash_v1"
_DEFAULT_CANONICAL_HASH_URL = "http://127.0.0.1:8000/api/policy/hash-snapshot"
_CANONICAL_HASH_URL_ENV = "PW_POLICY_HASH_SNAPSHOT_URL"

try:
    import pipeworks_ipc.hashing as ipc_hashing
except ImportError:  # pragma: no cover - import path is expected in normal runtime
    ipc_hashing = None


@dataclass(frozen=True, slots=True)
class PolicyHashEntry:
    """One normalized local policy file entry used for hash calculations."""

    relative_path: str
    content_hash: str


def build_sync_payload(
    *,
    source_root: Path,
    map_path_override: str | None,
    include_unchanged: bool,
) -> SyncPlanResponse:
    """Build serialized sync-plan payload for impact visualization."""

    mirror_map_path = resolve_mirror_map_path(explicit_map_path=map_path_override)
    mirror_map = load_mirror_map(mirror_map_path)
    plan = filter_sync_plan_to_supported_files(
        build_sync_plan(source_root=source_root, mirror_map=mirror_map)
    )

    actions = [
        serialize_action(action)
        for action in plan.actions
        if include_unchanged or action.action != SyncActionType.UNCHANGED
    ]

    return SyncPlanResponse(
        source_root=str(plan.source_root),
        map_path=str(plan.map_path),
        counts=counts_for_plan(plan),
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
    return filter_sync_plan_to_supported_files(plan)


def build_sync_compare_payload(
    *,
    source_root: Path,
    map_path_override: str | None,
    relative_path: str,
    focus_target: str | None = None,
) -> SyncCompareResponse:
    """Build side-by-side source/target comparison payload for one path."""

    validate_supported_editor_path(relative_path)
    mirror_map_path = resolve_mirror_map_path(explicit_map_path=map_path_override)
    mirror_map = load_mirror_map(mirror_map_path)

    plan = filter_sync_plan_to_supported_files(
        build_sync_plan(source_root=source_root, mirror_map=mirror_map)
    )
    action_by_target = action_by_target_for_relative_path(plan=plan, relative_path=relative_path)

    source_path = source_root / relative_path
    source_content = read_optional_text(source_path)
    source_exists = source_path.exists() and source_path.is_file()
    source_signature = content_signature(source_content=source_content, exists=source_exists)

    signatures_seen: dict[str, int] = {source_signature: 1}
    next_group_id = 2

    variants: list[SyncCompareVariantResponse] = [
        SyncCompareVariantResponse(
            label=canonical_source_label(source_root),
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
        target_content = read_optional_text(target_path)
        signature = content_signature(source_content=target_content, exists=target_exists)
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

    canonical_entries = collect_local_policy_entries(source_root)
    canonical_by_path = {entry.relative_path: entry for entry in canonical_entries}
    canonical_paths = set(canonical_by_path.keys())
    canonical_snapshot: HashCanonicalResponse | None = None
    canonical_url: str | None = None
    canonical_error: str | None = None

    try:
        canonical_url = resolve_canonical_hash_snapshot_url(canonical_snapshot_url_override)
        canonical_snapshot = fetch_canonical_hash_snapshot(canonical_url)
    except ValueError as exc:
        canonical_snapshot = None
        canonical_error = str(exc)

    target_statuses: list[HashTargetStatusResponse] = []
    for target in sorted(mirror_map.targets, key=lambda current: current.name):
        target_entries = collect_local_policy_entries(target.root)
        target_by_path = {entry.relative_path: entry for entry in target_entries}

        missing_count = 0
        different_count = 0
        projected_entries: list[PolicyHashEntry] = []

        for relative_path in sorted(canonical_paths):
            source_entry = canonical_by_path[relative_path]
            target_entry = target_by_path.get(relative_path)
            if target_entry is None:
                missing_count += 1
                # Missing canonical-managed files are represented by a stable
                # synthetic hash marker so tree-hash comparisons remain
                # deterministic across hosts and runs.
                projected_entries.append(
                    PolicyHashEntry(
                        relative_path=relative_path,
                        content_hash=compute_missing_content_hash(relative_path),
                    )
                )
                continue

            projected_entries.append(target_entry)
            if target_entry.content_hash != source_entry.content_hash:
                different_count += 1

        target_only_count = sum(1 for path in target_by_path if path not in canonical_paths)
        target_root_hash = compute_tree_hash(entries=projected_entries)
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
        # Drift is a strict hash mismatch against canonical snapshot root hash;
        # this intentionally ignores per-file reason details so the top-level
        # state remains a simple availability/alignment signal for operators.
        status = "ok" if all(target.matches_canonical for target in target_statuses) else "drift"

    return HashStatusResponse(
        status=status,
        canonical=canonical_snapshot,
        canonical_url=canonical_url,
        canonical_error=canonical_error,
        targets=target_statuses,
    )


def resolve_canonical_hash_snapshot_url(
    url_override: str | None,
    *,
    canonical_hash_url_env: str = _CANONICAL_HASH_URL_ENV,
    default_canonical_hash_url: str = _DEFAULT_CANONICAL_HASH_URL,
) -> str:
    """Resolve canonical hash snapshot URL from override, env var, or default."""

    candidate = url_override or os.getenv(canonical_hash_url_env) or default_canonical_hash_url
    normalized = (candidate or "").strip()
    if not normalized:
        raise ValueError("Canonical hash snapshot URL must not be empty")
    return normalized


def fetch_canonical_hash_snapshot(
    url: str,
    *,
    opener=urlopen,
    response_model=HashCanonicalResponse,
) -> HashCanonicalResponse:
    """Fetch and validate canonical mud-server hash snapshot payload."""

    request = Request(url=url, headers={"Accept": "application/json"})
    try:
        with opener(request, timeout=5.0) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to fetch canonical hash snapshot from {url}: {exc}") from exc

    validated = response_model.model_validate(payload)
    if not isinstance(validated, response_model):
        raise ValueError(f"Canonical hash snapshot from {url} did not match expected schema")
    return cast(HashCanonicalResponse, validated)


def collect_local_policy_entries(policy_root: Path) -> list[PolicyHashEntry]:
    """Collect deterministic policy file hash entries from ``policy_root``."""

    entries: list[PolicyHashEntry] = []
    for path in sorted(policy_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _EDITOR_FILE_SUFFIXES:
            continue

        relative_path = normalize_relative_path(path.relative_to(policy_root).as_posix())
        entries.append(
            PolicyHashEntry(
                relative_path=relative_path,
                content_hash=compute_file_hash(relative_path, path.read_bytes()),
            )
        )

    return entries


def compute_file_hash(
    relative_path: str,
    content_bytes: bytes,
    *,
    ipc_hashing_module=ipc_hashing,
    hash_version: str = _HASH_VERSION,
) -> str:
    """Compute deterministic policy file hash using IPC as primary contract."""

    helper = (
        getattr(ipc_hashing_module, "compute_policy_file_hash", None)
        if ipc_hashing_module
        else None
    )
    if callable(helper):
        return str(helper(relative_path, content_bytes))

    normalized_path = normalize_relative_path(relative_path)
    return str(
        compute_payload_hash(
            {
                "hash_version": hash_version,
                "relative_path": normalized_path,
                "content_bytes_hex": content_bytes.hex(),
            }
        )
    )


def compute_tree_hash(
    *,
    entries: list[PolicyHashEntry],
    ipc_hashing_module=ipc_hashing,
    hash_version: str = _HASH_VERSION,
) -> str:
    """Compute deterministic policy tree hash using IPC as primary contract."""

    helper = (
        getattr(ipc_hashing_module, "compute_policy_tree_hash", None)
        if ipc_hashing_module
        else None
    )
    entry_cls = getattr(ipc_hashing_module, "PolicyHashEntry", None) if ipc_hashing_module else None
    if callable(helper) and entry_cls is not None:
        ipc_entries = [
            entry_cls(relative_path=entry.relative_path, content_hash=entry.content_hash)
            for entry in entries
        ]
        return str(helper(ipc_entries))

    payload_entries = [
        {
            "relative_path": normalize_relative_path(entry.relative_path),
            "content_hash": entry.content_hash,
        }
        for entry in entries
    ]
    # Sort before hashing to make fallback behavior independent of filesystem
    # traversal order or caller-provided entry ordering.
    payload_entries.sort(key=lambda item: str(item["relative_path"]))
    return str(compute_payload_hash({"hash_version": hash_version, "entries": payload_entries}))


def compute_missing_content_hash(
    relative_path: str,
    *,
    hash_version: str = _HASH_VERSION,
) -> str:
    """Build deterministic hash marker for missing canonical-managed files."""

    normalized_path = normalize_relative_path(relative_path)
    return str(
        compute_payload_hash(
            {
                "hash_version": hash_version,
                "relative_path": normalized_path,
                "missing": True,
            }
        )
    )


def normalize_relative_path(relative_path: str) -> str:
    """Normalize a policy-relative path and reject traversal-like values."""

    as_posix = PurePosixPath(relative_path.replace("\\", "/")).as_posix()
    if as_posix.startswith("../") or "/../" in f"/{as_posix}":
        raise ValueError(f"Policy relative path must not traverse upwards: {relative_path!r}")

    normalized = as_posix.lstrip("./")
    if normalized in {"", "."}:
        raise ValueError("Policy relative path must not be empty")
    return normalized


def serialize_action(action: SyncAction) -> SyncActionResponse:
    """Convert planner action into JSON-serializable web response model."""

    return SyncActionResponse(
        target=action.target_name,
        relative_path=action.relative_path,
        action=action.action.value,
        source_path=str(action.source_path) if action.source_path else None,
        target_path=str(action.target_path) if action.target_path else None,
        reason=action.reason,
    )


def counts_for_plan(plan: SyncPlan) -> dict[str, int]:
    """Count action types from a sync plan."""

    counts = Counter(action.action for action in plan.actions)
    return {
        SyncActionType.CREATE.value: counts[SyncActionType.CREATE],
        SyncActionType.UPDATE.value: counts[SyncActionType.UPDATE],
        SyncActionType.UNCHANGED.value: counts[SyncActionType.UNCHANGED],
        SyncActionType.TARGET_ONLY.value: counts[SyncActionType.TARGET_ONLY],
    }


def is_supported_editor_file(
    relative_path: str,
    *,
    editor_file_suffixes: set[str] | tuple[str, ...] = _EDITOR_FILE_SUFFIXES,
) -> bool:
    """Return whether ``relative_path`` is supported by the web editor."""

    return Path(relative_path).suffix.lower() in set(editor_file_suffixes)


def validate_supported_editor_path(
    relative_path: str,
    *,
    editor_file_suffixes: set[str] | tuple[str, ...] = _EDITOR_FILE_SUFFIXES,
) -> None:
    """Raise ``ValueError`` when path is unsupported for web editor operations."""

    if not is_supported_editor_file(
        relative_path,
        editor_file_suffixes=editor_file_suffixes,
    ):
        raise ValueError(
            "Only .txt, .yaml, .yml, and .json policy files are supported by the web editor"
        )


def filter_snapshot_to_supported_files(
    snapshot: PolicyTreeSnapshot,
    *,
    editor_file_suffixes: set[str] | tuple[str, ...] = _EDITOR_FILE_SUFFIXES,
) -> PolicyTreeSnapshot:
    """Return snapshot narrowed to files supported by the web workbench editor."""

    supported_artifacts = [
        artifact
        for artifact in snapshot.artifacts
        if is_supported_editor_file(
            artifact.relative_path,
            editor_file_suffixes=editor_file_suffixes,
        )
    ]
    return PolicyTreeSnapshot(
        root=snapshot.root,
        directories=snapshot.directories,
        artifacts=supported_artifacts,
    )


def filter_sync_plan_to_supported_files(
    plan: SyncPlan,
    *,
    editor_file_suffixes: set[str] | tuple[str, ...] = _EDITOR_FILE_SUFFIXES,
) -> SyncPlan:
    """Return sync plan narrowed to files supported by the web workbench editor."""

    supported_actions = [
        action
        for action in plan.actions
        if is_supported_editor_file(action.relative_path, editor_file_suffixes=editor_file_suffixes)
    ]
    return SyncPlan(source_root=plan.source_root, map_path=plan.map_path, actions=supported_actions)


def action_by_target_for_relative_path(
    plan: SyncPlan,
    *,
    relative_path: str,
) -> dict[str, str]:
    """Return sync action type value keyed by target name for one relative path."""

    actions: dict[str, str] = {}
    for action in plan.actions:
        if action.relative_path != relative_path:
            continue
        actions[action.target_name] = action.action.value
    return actions


def read_optional_text(path: Path | None) -> str | None:
    """Read UTF-8 text from ``path`` when available, otherwise return ``None``."""

    if path is None:
        return None
    if not path.exists() or not path.is_file():
        return None

    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Unable to read text for diff: {path} ({exc})") from exc


def content_signature(*, source_content: str | None, exists: bool) -> str:
    """Build deterministic content signature used for grouping variants."""

    if not exists:
        return "__missing__"
    if source_content is None:
        return "__unreadable__"
    return str(compute_payload_hash({"content": source_content}))


def canonical_source_label(source_root: Path) -> str:
    """Build human-readable source column label for compare modal."""

    root_text = str(source_root).lower()
    if "pipeworks_mud_server" in root_text:
        return "canonical-source: mud-server"

    repo_name = source_root.parts[-3] if len(source_root.parts) >= 3 else source_root.name
    normalized = (
        repo_name.replace("pipeworks_", "").replace("pipeworks-", "").replace("_", "-").strip("-")
    )
    return f"canonical-source: {normalized or 'source'}"
