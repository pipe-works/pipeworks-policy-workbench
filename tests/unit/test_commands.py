"""Unit tests for doctor/validate command-module behavior."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from policy_workbench.commands.doctor import run_doctor
from policy_workbench.commands.validate import run_validate


def _write_text(path: Path, content: str) -> None:
    """Write UTF-8 test fixture content and create parents as needed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_run_doctor_reports_summary_for_valid_root(tmp_path: Path) -> None:
    """Doctor command should emit deterministic summary fields for valid roots."""

    policies_root = tmp_path / "policies"
    _write_text(policies_root / "image" / "prompts" / "portrait.txt", "good prompt")

    out = StringIO()
    err = StringIO()

    exit_code = run_doctor(root=str(policies_root), out=out, err=err)

    assert exit_code == 0
    assert "root:" in out.getvalue()
    assert "validation:" in out.getvalue()
    assert err.getvalue() == ""


def test_run_doctor_returns_2_when_root_missing() -> None:
    """Doctor command should return infra-style error code on root failures."""

    out = StringIO()
    err = StringIO()

    exit_code = run_doctor(root="/path/that/does/not/exist", out=out, err=err)

    assert exit_code == 2
    assert "doctor failed" in err.getvalue()


def test_run_validate_returns_1_when_error_issues_exist(tmp_path: Path) -> None:
    """Validate command should fail when any error-level issue is raised."""

    policies_root = tmp_path / "policies"
    _write_text(policies_root / "image" / "prompts" / "empty.txt", "")

    out = StringIO()
    err = StringIO()

    exit_code = run_validate(root=str(policies_root), out=out, err=err)

    assert exit_code == 1
    assert "PROMPT_TEXT_MISSING" in out.getvalue()
    assert err.getvalue() == ""


def test_run_validate_returns_0_for_clean_prompt_artifact(tmp_path: Path) -> None:
    """Validate command should pass for clean prompt-bearing artifacts."""

    policies_root = tmp_path / "policies"
    _write_text(policies_root / "image" / "prompts" / "ok.txt", "usable prompt text")

    out = StringIO()
    err = StringIO()

    exit_code = run_validate(root=str(policies_root), out=out, err=err)

    assert exit_code == 0
    assert "summary:" in out.getvalue()
    assert err.getvalue() == ""

