"""Unit tests for policy root path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

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
