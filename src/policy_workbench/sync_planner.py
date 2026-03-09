"""Deterministic sync planning engine.

The planner computes file-level actions across all configured targets without
mutating filesystem state. This enables safe review via `pw-policy sync`
default dry-run mode.
"""

from __future__ import annotations

from pathlib import Path

from .sync_models import MirrorMap, SyncAction, SyncActionType, SyncPlan


def build_sync_plan(source_root: Path, mirror_map: MirrorMap) -> SyncPlan:
    """Build deterministic sync actions for every configured target."""

    source_files = _collect_files(source_root)
    actions: list[SyncAction] = []

    for target in sorted(mirror_map.targets, key=lambda target: target.name):
        target_files = _collect_files(target.root)
        relative_paths = sorted(set(source_files) | set(target_files))

        for relative_path in relative_paths:
            source_path = source_files.get(relative_path)
            target_path = target_files.get(relative_path)

            if source_path and not target_path:
                actions.append(
                    SyncAction(
                        target_name=target.name,
                        relative_path=relative_path,
                        action=SyncActionType.CREATE,
                        source_path=source_path,
                        target_path=target.root / relative_path,
                    )
                )
                continue

            if source_path and target_path:
                if _file_contents_equal(source_path, target_path):
                    action_type = SyncActionType.UNCHANGED
                    reason = None
                else:
                    action_type = SyncActionType.UPDATE
                    reason = "content differs"

                actions.append(
                    SyncAction(
                        target_name=target.name,
                        relative_path=relative_path,
                        action=action_type,
                        source_path=source_path,
                        target_path=target_path,
                        reason=reason,
                    )
                )
                continue

            # Target-only files are detected and reported as explicit
            # delete-candidates, but are intentionally not removed by default.
            actions.append(
                SyncAction(
                    target_name=target.name,
                    relative_path=relative_path,
                    action=SyncActionType.DELETE_CANDIDATE,
                    source_path=None,
                    target_path=target_path,
                    reason="target-only file; destructive deletes are disabled by default",
                )
            )

    return SyncPlan(source_root=source_root, map_path=mirror_map.config_path, actions=actions)


def _collect_files(root: Path) -> dict[str, Path]:
    """Collect all regular files under ``root`` using relative POSIX paths."""

    files: dict[str, Path] = {}
    for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
        files[file_path.relative_to(root).as_posix()] = file_path
    return files


def _file_contents_equal(left: Path, right: Path) -> bool:
    """Compare two files by bytes for deterministic sync decisions."""

    try:
        return left.read_bytes() == right.read_bytes()
    except OSError:
        # If either file cannot be read, force an update action so apply mode
        # can rewrite target content from the known source state.
        return False
