"""Mirror-map contract loading and validation.

Phase 2 sync behavior is intentionally contract-driven. This module validates
``config/mirror_map.yaml`` and returns strongly-typed models consumed by the
planner and apply engine.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from .sync_models import MirrorMap, MirrorTarget

DEFAULT_MIRROR_MAP_PATH = Path(__file__).resolve().parents[2] / "config" / "mirror_map.yaml"


def resolve_mirror_map_path(explicit_map_path: str | None = None) -> Path:
    """Resolve mirror-map path from explicit input or project default.

    Args:
        explicit_map_path: Optional file path override passed via CLI.

    Returns:
        Existing resolved path to the mirror-map YAML file.

    Raises:
        FileNotFoundError: If the resolved file does not exist.
        IsADirectoryError: If the resolved path points to a directory.
    """

    candidate = (
        Path(os.path.expandvars(explicit_map_path)).expanduser()
        if explicit_map_path
        else DEFAULT_MIRROR_MAP_PATH
    )
    resolved = candidate.resolve()

    if not resolved.exists():
        raise FileNotFoundError(f"Mirror map not found: {resolved}")
    if resolved.is_dir():
        raise IsADirectoryError(f"Mirror map path is a directory: {resolved}")

    return resolved


def load_mirror_map(map_path: Path) -> MirrorMap:
    """Load and validate mirror-map YAML contract.

    Required structure:

    - ``version``: integer (currently must be ``1``)
    - ``targets``: list of objects with ``name`` and ``root``

    Optional structure:

    - ``source.root``: source policy root path (CLI ``--root`` still wins)
    """

    try:
        raw_data = yaml.safe_load(map_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Failed reading mirror map: {exc}") from exc

    if not isinstance(raw_data, dict):
        raise ValueError("Mirror map must be a YAML object at the top level")

    version = raw_data.get("version")
    if version != 1:
        raise ValueError(f"Unsupported mirror map version: {version!r}; expected 1")

    source_root = _parse_optional_source_root(raw_data)
    targets = _parse_targets(raw_data)

    return MirrorMap(config_path=map_path, source_root=source_root, targets=targets)


def _parse_optional_source_root(raw_data: dict[str, Any]) -> Path | None:
    """Parse optional ``source.root`` mapping entry."""

    source_section = raw_data.get("source")
    if source_section is None:
        return None

    if not isinstance(source_section, dict):
        raise ValueError("Mirror map 'source' must be an object when provided")

    raw_root = source_section.get("root")
    if raw_root is None:
        return None

    if not isinstance(raw_root, str) or not raw_root.strip():
        raise ValueError("Mirror map 'source.root' must be a non-empty string")

    return _resolve_existing_dir(raw_root, label="source.root")


def _parse_targets(raw_data: dict[str, Any]) -> list[MirrorTarget]:
    """Parse and validate configured mirror targets."""

    raw_targets = raw_data.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("Mirror map 'targets' must be a non-empty list")

    targets: list[MirrorTarget] = []
    seen_names: set[str] = set()

    for index, raw_target in enumerate(raw_targets):
        if not isinstance(raw_target, dict):
            raise ValueError(f"Mirror map target at index {index} must be an object")

        raw_name = raw_target.get("name")
        raw_root = raw_target.get("root")

        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError(f"Mirror map target at index {index} has invalid 'name'")
        if not isinstance(raw_root, str) or not raw_root.strip():
            raise ValueError(f"Mirror map target '{raw_name}' has invalid or missing 'root'")

        name = raw_name.strip()
        if name in seen_names:
            raise ValueError(f"Mirror map target name duplicated: {name}")

        seen_names.add(name)
        root_path = _resolve_existing_dir(raw_root, label=f"targets[{name}].root")
        targets.append(MirrorTarget(name=name, root=root_path))

    return targets


def _resolve_existing_dir(raw_path: str, *, label: str) -> Path:
    """Resolve ``raw_path`` and ensure it exists as a directory."""

    resolved = Path(os.path.expandvars(raw_path)).expanduser().resolve()

    if not resolved.exists():
        raise FileNotFoundError(f"Mirror map {label} directory not found: {resolved}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Mirror map {label} is not a directory: {resolved}")

    return resolved
