"""Unit tests for sync apply execution behavior."""

from __future__ import annotations

from pathlib import Path

from policy_workbench.sync_apply import apply_sync_plan
from policy_workbench.sync_models import SyncAction, SyncActionType, SyncPlan


def _write_text(path: Path, content: str) -> None:
    """Write UTF-8 fixture file and create parent directories."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_apply_sync_plan_executes_create_update_and_skips_non_destructive(
    tmp_path: Path,
) -> None:
    """Apply mode should write create/update actions and skip non-write actions."""

    source_root = tmp_path / "source"
    target_root = tmp_path / "target"

    _write_text(source_root / "create.txt", "create-value")
    _write_text(source_root / "update.txt", "new-value")
    _write_text(target_root / "update.txt", "old-value")
    _write_text(target_root / "leftover.txt", "leftover")

    plan = SyncPlan(
        source_root=source_root,
        map_path=tmp_path / "mirror_map.yaml",
        actions=[
            SyncAction(
                target_name="target-a",
                relative_path="create.txt",
                action=SyncActionType.CREATE,
                source_path=source_root / "create.txt",
                target_path=target_root / "create.txt",
            ),
            SyncAction(
                target_name="target-a",
                relative_path="update.txt",
                action=SyncActionType.UPDATE,
                source_path=source_root / "update.txt",
                target_path=target_root / "update.txt",
            ),
            SyncAction(
                target_name="target-a",
                relative_path="leftover.txt",
                action=SyncActionType.TARGET_ONLY,
                source_path=None,
                target_path=target_root / "leftover.txt",
                reason="target-only file",
            ),
        ],
    )

    report = apply_sync_plan(plan)

    assert report.created == 1
    assert report.updated == 1
    assert report.skipped == 1
    assert (target_root / "create.txt").read_text(encoding="utf-8") == "create-value"
    assert (target_root / "update.txt").read_text(encoding="utf-8") == "new-value"
    assert (target_root / "leftover.txt").read_text(encoding="utf-8") == "leftover"
