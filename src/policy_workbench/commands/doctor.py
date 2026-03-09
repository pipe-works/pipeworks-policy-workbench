"""Doctor command implementation.

The doctor command gives a high-signal summary of the current canonical policy
root and highlights validation health without mutating anything.
"""

from __future__ import annotations

from collections import Counter
from typing import TextIO

from ..models import IssueLevel
from ..pathing import resolve_policy_root
from ..tree_model import build_policy_tree_snapshot
from ..validators import validate_snapshot


def run_doctor(*, root: str | None, out: TextIO, err: TextIO) -> int:
    """Run repository diagnostics and print a compact health summary.

    Returns:
        ``0`` when scan and validation complete without error-level issues.
        ``1`` when validation reports errors.
        ``2`` when root resolution/scanning fails.
    """

    try:
        policy_root = resolve_policy_root(explicit_root=root)
        snapshot = build_policy_tree_snapshot(policy_root)
    except (FileNotFoundError, NotADirectoryError, RuntimeError, ValueError, OSError) as exc:
        err.write(f"pw-policy: doctor failed: {exc}\n")
        return 2

    report = validate_snapshot(snapshot)

    role_counts = Counter(artifact.role.value for artifact in snapshot.artifacts)

    out.write(f"root: {snapshot.root}\n")
    out.write(f"directories: {len(snapshot.directories)}\n")
    out.write(f"artifacts: {len(snapshot.artifacts)}\n")

    out.write("roles:\n")
    for role, count in sorted(role_counts.items()):
        out.write(f"  {role}: {count}\n")

    info_count = report.count(IssueLevel.INFO)
    warning_count = report.count(IssueLevel.WARNING)
    error_count = report.count(IssueLevel.ERROR)
    out.write("validation: " f"errors={error_count} warnings={warning_count} info={info_count}\n")

    return 1 if report.has_errors else 0
