"""Sync command handler.

Phase 1 keeps sync intentionally non-destructive and explicit. The real sync
planner/apply engine is scheduled for Phase 2.
"""

from __future__ import annotations

from typing import TextIO


def run_sync(*, out: TextIO) -> int:
    """Print a deterministic placeholder until sync implementation lands."""

    out.write("pw-policy: sync not implemented yet\n")
    return 0
