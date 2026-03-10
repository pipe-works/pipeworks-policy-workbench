"""Service-layer helpers for the Phase 3 policy workbench web app."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .mirror_map import load_mirror_map, resolve_mirror_map_path
from .models import IssueLevel, PolicyTreeSnapshot
from .pathing import resolve_policy_root
from .sync_models import SyncAction, SyncActionType, SyncPlan
from .sync_planner import build_sync_plan
from .tree_model import build_policy_tree_snapshot
from .validators import validate_snapshot
from .web_models import (
    PolicyArtifactResponse,
    PolicyTreeResponse,
    SyncActionResponse,
    SyncCompareResponse,
    SyncCompareVariantResponse,
    SyncPlanResponse,
    ValidationIssueResponse,
    ValidationResponse,
)

_EDITOR_FILE_SUFFIXES = {".txt", ".yaml", ".yml"}


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
        if _is_supported_editor_file(artifact.relative_path)
    ]

    # The tree sidebar is intentionally scoped to editable policy files only.
    directory_set = {"policies"}
    for artifact in artifacts:
        parent = Path(artifact.relative_path).parent.as_posix()
        if parent and parent != ".":
            directory_set.add(parent)

    return PolicyTreeResponse(
        source_root=str(snapshot.root),
        directories=sorted(directory_set),
        artifacts=artifacts,
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


def _is_supported_editor_file(relative_path: str) -> bool:
    """Return whether ``relative_path`` should be visible/editable in the web editor."""

    return Path(relative_path).suffix.lower() in _EDITOR_FILE_SUFFIXES


def _validate_supported_editor_path(relative_path: str) -> None:
    """Raise ``ValueError`` when web editor is asked to read/write unsupported files."""

    if not _is_supported_editor_file(relative_path):
        raise ValueError("Only .txt, .yaml, and .yml policy files are supported by the web editor")


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
    return source_content if source_content is not None else "__unreadable__"


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
