"""Test configuration for local src package imports."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def _reset_runtime_mode_state():
    """Ensure runtime source-mode globals start clean for every test."""
    from policy_workbench import runtime_mode

    runtime_mode._reset_runtime_mode_for_tests()
    yield
    runtime_mode._reset_runtime_mode_for_tests()
