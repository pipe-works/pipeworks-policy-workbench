"""Service-layer helpers for the Phase 3 policy workbench web app."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .mirror_map import load_mirror_map, resolve_mirror_map_path
from .models import IssueLevel
from .pathing import resolve_policy_root
from .sync_models import SyncAction, SyncActionType, SyncPlan
from .sync_planner import build_sync_plan
from .tree_model import build_policy_tree_snapshot
from .validators import validate_snapshot
from .web_models import (
    PolicyArtifactResponse,
    PolicyTreeResponse,
    SyncActionResponse,
    SyncPlanResponse,
    ValidationIssueResponse,
    ValidationResponse,
)


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
    artifacts = [
        PolicyArtifactResponse(
            relative_path=artifact.relative_path,
            role=artifact.role.value,
            has_prompt_text=bool((artifact.prompt_text or "").strip()),
        )
        for artifact in snapshot.artifacts
    ]

    return PolicyTreeResponse(
        source_root=str(snapshot.root),
        directories=snapshot.directories,
        artifacts=artifacts,
    )


def read_policy_file(source_root: Path, relative_path: str) -> str:
    """Read one policy file by relative path with traversal protection."""

    file_path = _resolve_file_under_root(source_root=source_root, relative_path=relative_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Policy file not found: {relative_path}")
    if not file_path.is_file():
        raise IsADirectoryError(f"Policy path is not a file: {relative_path}")

    return file_path.read_text(encoding="utf-8")


def write_policy_file(source_root: Path, relative_path: str, content: str) -> int:
    """Write one policy file under source root and return bytes written."""

    file_path = _resolve_file_under_root(source_root=source_root, relative_path=relative_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return len(content.encode("utf-8"))


def build_validation_payload(source_root: Path) -> ValidationResponse:
    """Build serialized validation payload for right-panel reporting."""

    snapshot = build_policy_tree_snapshot(source_root)
    report = validate_snapshot(snapshot)

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
    plan = build_sync_plan(source_root=source_root, mirror_map=mirror_map)

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
    return build_sync_plan(source_root=source_root, mirror_map=mirror_map)


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
        SyncActionType.DELETE_CANDIDATE.value: counts[SyncActionType.DELETE_CANDIDATE],
    }
