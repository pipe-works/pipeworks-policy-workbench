"""Data models for sync mapping, planning, and execution.

These models keep sync flows explicit and serializable for both CLI output and
future API/web surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class SyncActionType(StrEnum):
    """Discrete file-level actions produced by sync planning."""

    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"
    TARGET_ONLY = "target_only"


@dataclass(slots=True)
class MirrorTarget:
    """One configured sync destination root."""

    name: str
    root: Path


@dataclass(slots=True)
class MirrorMap:
    """Resolved mirror-map contract loaded from ``config/mirror_map.yaml``."""

    config_path: Path
    source_root: Path | None
    targets: list[MirrorTarget]


@dataclass(slots=True)
class SyncAction:
    """One deterministic file-level change (or no-op) in a sync plan."""

    target_name: str
    relative_path: str
    action: SyncActionType
    source_path: Path | None
    target_path: Path | None
    reason: str | None = None


@dataclass(slots=True)
class SyncPlan:
    """Complete sync plan for all configured targets."""

    source_root: Path
    map_path: Path
    actions: list[SyncAction]

    def actions_for_target(self, target_name: str) -> list[SyncAction]:
        """Return all actions for one target in stable order."""

        return [action for action in self.actions if action.target_name == target_name]


@dataclass(slots=True)
class SyncApplyReport:
    """Result summary for an ``--apply`` sync execution."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
