"""Source-root, tree, file, and validation helpers for web routes.

This module keeps filesystem-backed source operations isolated so
``web_services`` can remain an orchestration compatibility layer while Phase 2
decomposition finishes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .mirror_map import load_mirror_map, resolve_mirror_map_path
from .models import IssueLevel, PolicyTreeSnapshot
from .pathing import resolve_policy_root
from .policy_authoring import selector_from_relative_path
from .sync_models import MirrorMap
from .tree_model import build_policy_tree_snapshot
from .validators import validate_snapshot
from .web_models import (
    PolicyArtifactResponse,
    PolicyTreeResponse,
    ValidationIssueResponse,
    ValidationResponse,
)


def resolve_source_root_for_web(
    *,
    root_override: str | None,
    map_path_override: str | None,
    resolve_policy_root_fn: Callable[..., Path] = resolve_policy_root,
    resolve_mirror_map_path_fn: Callable[..., Path] = resolve_mirror_map_path,
    load_mirror_map_fn: Callable[[Path], MirrorMap] = load_mirror_map,
) -> Path:
    """Resolve canonical source root for web APIs.

    Resolution precedence:
    1. Explicit ``root_override``
    2. ``source.root`` in mirror-map config
    3. Default pathing resolution from ``resolve_policy_root``
    """

    if root_override:
        return resolve_policy_root_fn(explicit_root=root_override)

    resolved_map_path = resolve_mirror_map_path_fn(explicit_map_path=map_path_override)
    mirror_map = load_mirror_map_fn(resolved_map_path)
    if mirror_map.source_root is not None:
        return mirror_map.source_root

    return resolve_policy_root_fn(explicit_root=None)


def build_tree_payload(
    source_root: Path,
    *,
    is_supported_editor_file: Callable[[str], bool],
    selector_from_relative_path_fn=selector_from_relative_path,
    build_policy_tree_snapshot_fn=build_policy_tree_snapshot,
) -> PolicyTreeResponse:
    """Build serialized tree-browser payload for the web UI."""

    snapshot = build_policy_tree_snapshot_fn(source_root)
    artifacts: list[PolicyArtifactResponse] = []
    for artifact in snapshot.artifacts:
        if not is_supported_editor_file(artifact.relative_path):
            continue
        selector = selector_from_relative_path_fn(artifact.relative_path)
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


def read_policy_file(
    source_root: Path,
    relative_path: str,
    *,
    validate_supported_editor_path: Callable[[str], None],
    resolve_file_under_root: Callable[[Path, str], Path],
) -> str:
    """Read one policy file by relative path with traversal protection."""

    validate_supported_editor_path(relative_path)
    file_path = resolve_file_under_root(source_root, relative_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Policy file not found: {relative_path}")
    if not file_path.is_file():
        raise IsADirectoryError(f"Policy path is not a file: {relative_path}")

    return file_path.read_text(encoding="utf-8")


def write_policy_file(
    source_root: Path,
    relative_path: str,
    content: str,
    *,
    validate_supported_editor_path: Callable[[str], None],
    resolve_file_under_root: Callable[[Path, str], Path],
) -> int:
    """Write one policy file under source root and return bytes written."""

    validate_supported_editor_path(relative_path)
    file_path = resolve_file_under_root(source_root, relative_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return len(content.encode("utf-8"))


def build_validation_payload(
    source_root: Path,
    *,
    filter_snapshot_to_supported_files: Callable[[PolicyTreeSnapshot], PolicyTreeSnapshot],
    build_policy_tree_snapshot_fn=build_policy_tree_snapshot,
    validate_snapshot_fn=validate_snapshot,
) -> ValidationResponse:
    """Build serialized validation payload for right-panel reporting."""

    snapshot = build_policy_tree_snapshot_fn(source_root)
    report = validate_snapshot_fn(filter_snapshot_to_supported_files(snapshot))

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

    return ValidationResponse(
        source_root=str(report.root),
        source_kind="local_mirror_snapshot",
        canonical_authority="mud_server_policy_api",
        detail=(
            "Validation inspects local mirror files only; canonical policy authority "
            "remains mud-server policy APIs."
        ),
        counts=counts,
        issues=issues,
    )


def resolve_file_under_root(source_root: Path, relative_path: str) -> Path:
    """Resolve a file path safely under ``source_root``.

    Raises ``ValueError`` when the resolved path escapes source_root.
    """

    candidate = (source_root / relative_path).resolve()
    if source_root not in candidate.parents and candidate != source_root:
        raise ValueError(f"Relative path escapes source root: {relative_path}")
    return candidate
