"""Unit tests for deterministic sync planning."""

from __future__ import annotations

from pathlib import Path

from policy_workbench.sync_models import MirrorMap, MirrorTarget, SyncActionType
from policy_workbench.sync_planner import build_sync_plan


def _write_text(path: Path, content: str) -> None:
    """Write UTF-8 fixture file with automatic parent creation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_sync_plan_detects_create_update_unchanged_and_target_onlys(
    tmp_path: Path,
) -> None:
    """Planner should classify all core sync action types in one pass."""

    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir(parents=True)
    target_root.mkdir(parents=True)

    _write_text(source_root / "same.txt", "same")
    _write_text(source_root / "create.txt", "create")
    _write_text(source_root / "update.txt", "new")

    _write_text(target_root / "same.txt", "same")
    _write_text(target_root / "update.txt", "old")
    _write_text(target_root / "extra.txt", "target-only")

    mirror_map = MirrorMap(
        config_path=tmp_path / "mirror_map.yaml",
        source_root=source_root,
        targets=[MirrorTarget(name="target-a", root=target_root)],
    )

    plan = build_sync_plan(source_root=source_root, mirror_map=mirror_map)

    by_relpath = {action.relative_path: action for action in plan.actions}
    assert by_relpath["create.txt"].action == SyncActionType.CREATE
    assert by_relpath["same.txt"].action == SyncActionType.UNCHANGED
    assert by_relpath["update.txt"].action == SyncActionType.UPDATE
    assert by_relpath["extra.txt"].action == SyncActionType.TARGET_ONLY


def test_build_sync_plan_is_stable_ordered_by_target_then_path(tmp_path: Path) -> None:
    """Action ordering should be deterministic for reproducible reporting."""

    source_root = tmp_path / "source"
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    source_root.mkdir(parents=True)
    target_a.mkdir(parents=True)
    target_b.mkdir(parents=True)

    _write_text(source_root / "b.txt", "B")
    _write_text(source_root / "a.txt", "A")

    mirror_map = MirrorMap(
        config_path=tmp_path / "mirror_map.yaml",
        source_root=source_root,
        targets=[
            MirrorTarget(name="target-b", root=target_b),
            MirrorTarget(name="target-a", root=target_a),
        ],
    )

    plan = build_sync_plan(source_root=source_root, mirror_map=mirror_map)

    ordered_pairs = [(action.target_name, action.relative_path) for action in plan.actions]
    assert ordered_pairs == [
        ("target-a", "a.txt"),
        ("target-a", "b.txt"),
        ("target-b", "a.txt"),
        ("target-b", "b.txt"),
    ]
