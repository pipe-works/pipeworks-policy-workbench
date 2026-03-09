"""Validate command implementation.

This command emits deterministic, line-oriented results suitable for both
humans and automation that needs stable, parseable output.
"""

from __future__ import annotations

from typing import TextIO

from ..models import IssueLevel, ValidationIssue
from ..pathing import resolve_policy_root
from ..tree_model import build_policy_tree_snapshot
from ..validators import validate_snapshot


def run_validate(*, root: str | None, out: TextIO, err: TextIO) -> int:
    """Validate canonical policy content and emit issue lines.

    Returns:
        ``0`` when no error-level issues are found.
        ``1`` when one or more error-level issues are found.
        ``2`` when root resolution or scanning fails.
    """

    try:
        policy_root = resolve_policy_root(explicit_root=root)
        snapshot = build_policy_tree_snapshot(policy_root)
    except (FileNotFoundError, NotADirectoryError, RuntimeError, ValueError, OSError) as exc:
        err.write(f"pw-policy: validate failed: {exc}\n")
        return 2

    report = validate_snapshot(snapshot)

    for issue in sorted(report.issues, key=_issue_sort_key):
        location = issue.relative_path or "<root>"
        out.write(f"[{issue.level.value.upper()}] {issue.code} {location}: {issue.message}\n")

    out.write(
        "summary: "
        f"errors={report.count(IssueLevel.ERROR)} "
        f"warnings={report.count(IssueLevel.WARNING)} "
        f"info={report.count(IssueLevel.INFO)}\n"
    )

    return 1 if report.has_errors else 0


def _issue_sort_key(issue: ValidationIssue) -> tuple[str, str, str]:
    """Stable sort key for deterministic validation output."""

    return (issue.relative_path or "", issue.level.value, issue.code)
