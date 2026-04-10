"""Path resolution helpers for policy workbench commands.

This module centralizes root-path resolution so all commands (CLI and future
web/API layers) share one deterministic source of truth.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_POLICY_ROOT = "PW_POLICY_CANONICAL_ROOT"
DEFAULT_WORLD_ID = "pipeworks_web"
LUMINAL_WORKSPACE_ROOT = Path("/srv/work/pipeworks/repos")


def _default_policy_root_candidates() -> tuple[Path, ...]:
    """Return deterministic default root candidates for workspace-local execution.

    Candidate order:
    1. canonical Luminal PipeWorks workspace path
    2. sibling mud-server repository in the common workspace layout
    3. in-repo fallback path (useful for fixture-style local setups)
    """

    repo_root = Path(__file__).resolve().parents[2]
    workspace_root = repo_root.parent

    luminal_default = (
        LUMINAL_WORKSPACE_ROOT
        / "pipeworks_mud_server"
        / "data"
        / "worlds"
        / DEFAULT_WORLD_ID
        / "policies"
    )
    mud_server_default = (
        workspace_root / "pipeworks_mud_server" / "data" / "worlds" / DEFAULT_WORLD_ID / "policies"
    )
    local_repo_default = repo_root / "data" / "worlds" / DEFAULT_WORLD_ID / "policies"

    return (luminal_default, mud_server_default, local_repo_default)


def _validate_existing_dir(path: Path, *, source_label: str) -> Path:
    """Validate that ``path`` exists as a directory and return its resolved form."""

    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"{source_label} not found: {resolved}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"{source_label} is not a directory: {resolved}")
    return resolved


def resolve_policy_root(explicit_root: str | None = None) -> Path:
    """Resolve the canonical policy root directory.

    Resolution order:
    1. explicit CLI argument (`explicit_root`)
    2. environment variable (`PW_POLICY_CANONICAL_ROOT`)
    3. workspace-local default candidates (`_default_policy_root_candidates`)

    Raises:
        FileNotFoundError: when resolved path does not exist.
        NotADirectoryError: when resolved path exists but is not a directory.
    """

    raw_value = explicit_root or os.getenv(ENV_POLICY_ROOT)
    if raw_value:
        candidate = Path(os.path.expandvars(raw_value)).expanduser()
        try:
            return _validate_existing_dir(candidate, source_label="Canonical policy root")
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"{exc}. Provide --root or set {ENV_POLICY_ROOT}.") from exc

    checked_defaults: list[Path] = []
    for candidate in _default_policy_root_candidates():
        checked_defaults.append(candidate.resolve())
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()

    checked_text = ", ".join(str(path) for path in checked_defaults)
    raise FileNotFoundError(
        "Canonical policy root not found in default locations. "
        f"Checked: {checked_text}. Provide --root or set {ENV_POLICY_ROOT}."
    )
