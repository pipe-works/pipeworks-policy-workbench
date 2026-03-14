"""Unit tests for policy root path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from policy_workbench import pathing
from policy_workbench.pathing import ENV_POLICY_ROOT, resolve_policy_root


def test_resolve_policy_root_uses_explicit_value(tmp_path: Path) -> None:
    """Explicit root argument should override environment/default behavior."""

    resolved = resolve_policy_root(explicit_root=str(tmp_path))
    assert resolved == tmp_path.resolve()


def test_resolve_policy_root_uses_environment_value(monkeypatch, tmp_path: Path) -> None:
    """Environment override should be honored when explicit root is absent."""

    monkeypatch.setenv(ENV_POLICY_ROOT, str(tmp_path))
    resolved = resolve_policy_root()
    assert resolved == tmp_path.resolve()


def test_resolve_policy_root_raises_for_missing_dir(monkeypatch) -> None:
    """Missing directories should produce FileNotFoundError with guidance."""

    monkeypatch.setenv(ENV_POLICY_ROOT, "/path/that/does/not/exist")
    with pytest.raises(FileNotFoundError):
        resolve_policy_root()


def test_resolve_policy_root_raises_when_explicit_path_is_file(tmp_path: Path) -> None:
    """Explicit root path must point to a directory."""

    file_path = tmp_path / "not_a_directory.txt"
    file_path.write_text("content", encoding="utf-8")

    with pytest.raises(NotADirectoryError, match="not a directory"):
        resolve_policy_root(explicit_root=str(file_path))


def test_resolve_policy_root_uses_default_candidates_when_unset(
    monkeypatch, tmp_path: Path
) -> None:
    """Fallback should use the first existing default candidate deterministically."""

    first_missing = tmp_path / "missing-default"
    second_existing = tmp_path / "existing-default"
    second_existing.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv(ENV_POLICY_ROOT, raising=False)
    monkeypatch.setattr(
        pathing,
        "_default_policy_root_candidates",
        lambda: (first_missing, second_existing),
    )

    resolved = resolve_policy_root()
    assert resolved == second_existing.resolve()


def test_resolve_policy_root_surfaces_checked_defaults_when_none_exist(
    monkeypatch, tmp_path: Path
) -> None:
    """Missing default candidates should produce actionable checked-path guidance."""

    default_a = tmp_path / "missing-a"
    default_b = tmp_path / "missing-b"

    monkeypatch.delenv(ENV_POLICY_ROOT, raising=False)
    monkeypatch.setattr(
        pathing,
        "_default_policy_root_candidates",
        lambda: (default_a, default_b),
    )

    with pytest.raises(FileNotFoundError, match="Checked:"):
        resolve_policy_root()
