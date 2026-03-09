"""Sync apply engine.

Apply mode executes only non-destructive create/update operations. Delete
candidates remain visible in reports but are skipped unless destructive behavior
is explicitly designed and implemented in a future phase.
"""

from __future__ import annotations

from .sync_models import SyncAction, SyncActionType, SyncApplyReport, SyncPlan


def apply_sync_plan(plan: SyncPlan) -> SyncApplyReport:
    """Apply a sync plan in-place for create/update actions only."""

    report = SyncApplyReport()

    for action in plan.actions:
        if action.action == SyncActionType.CREATE:
            _write_from_source(action)
            report.created += 1
            continue

        if action.action == SyncActionType.UPDATE:
            _write_from_source(action)
            report.updated += 1
            continue

        report.skipped += 1

    return report


def _write_from_source(action: SyncAction) -> None:
    """Copy source file bytes to target path for one create/update action."""

    source_path = action.source_path
    target_path = action.target_path

    if source_path is None or target_path is None:
        raise RuntimeError("Create/update action missing source or target path")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(source_path.read_bytes())
