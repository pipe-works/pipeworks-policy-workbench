"""Path resolution helpers for policy workbench commands.

This module centralizes root-path resolution so all commands (CLI and future
web/API layers) share one deterministic source of truth.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_POLICY_ROOT = "PW_POLICY_CANONICAL_ROOT"
DEFAULT_POLICY_ROOT = Path(
    "/Users/aapark/pipe-works-development/pipeworks_mud_server/"
    "data/worlds/pipeworks_web/policies"
)


def resolve_policy_root(explicit_root: str | None = None) -> Path:
    """Resolve the canonical policy root directory.

    Resolution order:
    1. explicit CLI argument (`explicit_root`)
    2. environment variable (`PW_POLICY_CANONICAL_ROOT`)
    3. repository default path (`DEFAULT_POLICY_ROOT`)

    Raises:
        FileNotFoundError: when resolved path does not exist.
        NotADirectoryError: when resolved path exists but is not a directory.
    """

    raw_value = explicit_root or os.getenv(ENV_POLICY_ROOT)

    # Prefer explicit values first; this supports ad-hoc validation against
    # fixture trees or temporary working directories.
    candidate = Path(raw_value).expanduser() if raw_value else DEFAULT_POLICY_ROOT
    resolved = candidate.resolve()

    if not resolved.exists():
        raise FileNotFoundError(
            "Canonical policy root not found: "
            f"{resolved}. Provide --root or set {ENV_POLICY_ROOT}."
        )

    if not resolved.is_dir():
        raise NotADirectoryError(f"Canonical policy root is not a directory: {resolved}")

    return resolved
