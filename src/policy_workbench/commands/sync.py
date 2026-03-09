"""Sync command handler.

Phase 2 introduces deterministic sync planning with explicit safety gates:
- default mode is dry-run
- apply mode requires an explicit confirmation flag
- destructive deletes are reported but not executed
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, TextIO

from ..mirror_map import load_mirror_map, resolve_mirror_map_path
from ..pathing import resolve_policy_root
from ..sync_apply import apply_sync_plan
from ..sync_models import SyncAction, SyncActionType, SyncPlan
from ..sync_planner import build_sync_plan


def run_sync(
    *,
    root: str | None,
    map_path: str | None,
    output_format: str,
    apply: bool,
    yes: bool,
    include_unchanged: bool,
    out: TextIO,
    err: TextIO,
) -> int:
    """Run sync in dry-run or apply mode and emit deterministic reporting.

    Exit codes:
    - ``0``: successful planning/execution
    - ``2``: invalid args, path/config, or execution failure
    """

    if apply and not yes:
        err.write("pw-policy: sync apply requires --yes safety confirmation\n")
        return 2

    try:
        resolved_map_path = resolve_mirror_map_path(explicit_map_path=map_path)
        mirror_map = load_mirror_map(resolved_map_path)
        source_root = _resolve_sync_source_root(
            root_override=root,
            mapped_root=mirror_map.source_root,
        )
        plan = build_sync_plan(source_root=source_root, mirror_map=mirror_map)
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError, ValueError, OSError) as exc:
        err.write(f"pw-policy: sync failed: {exc}\n")
        return 2

    if output_format == "json":
        _write_json_report(plan=plan, include_unchanged=include_unchanged, out=out)
    else:
        _write_text_report(plan=plan, include_unchanged=include_unchanged, out=out)

    if not apply:
        return 0

    try:
        apply_report = apply_sync_plan(plan)
    except OSError as exc:
        err.write(f"pw-policy: sync apply failed: {exc}\n")
        return 2

    out.write(
        "apply-summary: "
        f"created={apply_report.created} "
        f"updated={apply_report.updated} "
        f"skipped={apply_report.skipped}\n"
    )

    return 0


def _resolve_sync_source_root(root_override: str | None, mapped_root: Path | None) -> Path:
    """Resolve source root precedence for sync execution."""

    if root_override:
        return resolve_policy_root(explicit_root=root_override)

    if mapped_root is not None:
        if not mapped_root.exists():
            raise FileNotFoundError(f"Mirror map source root not found: {mapped_root}")
        if not mapped_root.is_dir():
            raise NotADirectoryError(f"Mirror map source root is not a directory: {mapped_root}")
        return mapped_root

    return resolve_policy_root(explicit_root=None)


def _write_text_report(plan: SyncPlan, include_unchanged: bool, out: TextIO) -> None:
    """Render human-readable sync report."""

    out.write(f"source: {plan.source_root}\n")
    out.write(f"map: {plan.map_path}\n")

    action_counts = Counter(action.action for action in plan.actions)
    out.write(
        "summary: "
        f"create={action_counts[SyncActionType.CREATE]} "
        f"update={action_counts[SyncActionType.UPDATE]} "
        f"unchanged={action_counts[SyncActionType.UNCHANGED]} "
        f"delete_candidate={action_counts[SyncActionType.DELETE_CANDIDATE]}\n"
    )

    for action in plan.actions:
        if action.action == SyncActionType.UNCHANGED and not include_unchanged:
            continue

        reason_suffix = f" ({action.reason})" if action.reason else ""
        out.write(
            f"[{action.target_name}] {action.action.value} {action.relative_path}{reason_suffix}\n"
        )


def _write_json_report(plan: SyncPlan, include_unchanged: bool, out: TextIO) -> None:
    """Render machine-readable sync report."""

    actions_payload = [
        _action_to_payload(action)
        for action in plan.actions
        if include_unchanged or action.action != SyncActionType.UNCHANGED
    ]

    payload = {
        "source_root": str(plan.source_root),
        "map_path": str(plan.map_path),
        "actions": actions_payload,
        "counts": _counts_payload(plan.actions),
    }
    out.write(json.dumps(payload, indent=2, sort_keys=True))
    out.write("\n")


def _action_to_payload(action: SyncAction) -> dict[str, Any]:
    """Convert one action to JSON-safe payload."""

    return {
        "target": action.target_name,
        "relative_path": action.relative_path,
        "action": action.action.value,
        "source_path": str(action.source_path) if action.source_path else None,
        "target_path": str(action.target_path) if action.target_path else None,
        "reason": action.reason,
    }


def _counts_payload(actions: list[SyncAction]) -> dict[str, int]:
    """Summarize action counts for JSON output."""

    counts = Counter(action.action for action in actions)
    return {
        SyncActionType.CREATE.value: counts[SyncActionType.CREATE],
        SyncActionType.UPDATE.value: counts[SyncActionType.UPDATE],
        SyncActionType.UNCHANGED.value: counts[SyncActionType.UNCHANGED],
        SyncActionType.DELETE_CANDIDATE.value: counts[SyncActionType.DELETE_CANDIDATE],
    }
