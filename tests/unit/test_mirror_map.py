"""Unit tests for mirror-map contract loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from policy_workbench.mirror_map import load_mirror_map, resolve_mirror_map_path


def _write_text(path: Path, content: str) -> None:
    """Write UTF-8 fixture content with parent creation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_resolve_mirror_map_path_with_explicit_file(tmp_path: Path) -> None:
    """Explicit map path should resolve and be returned when file exists."""

    map_file = tmp_path / "mirror_map.yaml"
    _write_text(map_file, "version: 1\ntargets: []\n")

    resolved = resolve_mirror_map_path(str(map_file))
    assert resolved == map_file.resolve()


def test_load_mirror_map_parses_source_and_targets(tmp_path: Path) -> None:
    """Loader should return typed source/target roots for a valid contract."""

    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir(parents=True)
    target_root.mkdir(parents=True)

    map_file = tmp_path / "mirror_map.yaml"
    _write_text(
        map_file,
        (
            "version: 1\n"
            "source:\n"
            f"  root: {source_root}\n"
            "targets:\n"
            "  - name: tgt\n"
            f"    root: {target_root}\n"
        ),
    )

    mirror_map = load_mirror_map(map_file)

    assert mirror_map.source_root == source_root.resolve()
    assert len(mirror_map.targets) == 1
    assert mirror_map.targets[0].name == "tgt"
    assert mirror_map.targets[0].root == target_root.resolve()


def test_load_mirror_map_rejects_unsupported_version(tmp_path: Path) -> None:
    """Unsupported versions should fail fast with actionable errors."""

    map_file = tmp_path / "mirror_map.yaml"
    _write_text(map_file, "version: 2\ntargets: []\n")

    with pytest.raises(ValueError, match="Unsupported mirror map version"):
        load_mirror_map(map_file)


def test_load_mirror_map_rejects_missing_target_directory(tmp_path: Path) -> None:
    """Missing target roots should raise to prevent accidental wrong-path sync."""

    source_root = tmp_path / "source"
    source_root.mkdir(parents=True)

    missing_target = tmp_path / "missing-target"
    map_file = tmp_path / "mirror_map.yaml"

    _write_text(
        map_file,
        (
            "version: 1\n"
            "source:\n"
            f"  root: {source_root}\n"
            "targets:\n"
            "  - name: tgt\n"
            f"    root: {missing_target}\n"
        ),
    )

    with pytest.raises(FileNotFoundError, match=r"targets\[tgt\]\.root"):
        load_mirror_map(map_file)
