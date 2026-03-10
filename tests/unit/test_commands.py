"""Unit tests for command-module behavior."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from policy_workbench.commands.doctor import run_doctor
from policy_workbench.commands.sync import run_sync
from policy_workbench.commands.validate import run_validate


def _write_text(path: Path, content: str) -> None:
    """Write UTF-8 test fixture content and create parents as needed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_mirror_map(path: Path, source_root: Path, target_root: Path) -> None:
    """Create a minimal valid mirror map for sync tests."""

    content = (
        "version: 1\n"
        "source:\n"
        f"  root: {source_root}\n"
        "targets:\n"
        "  - name: target-a\n"
        f"    root: {target_root}\n"
    )
    _write_text(path, content)


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


def test_run_sync_dry_run_text_reports_create_update_target_only(tmp_path: Path) -> None:
    """Sync dry-run should produce deterministic human-readable action lines."""

    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    map_path = tmp_path / "mirror_map.yaml"

    _write_text(source_root / "same.txt", "same")
    _write_text(source_root / "update.txt", "new")
    _write_text(source_root / "create.txt", "create")

    _write_text(target_root / "same.txt", "same")
    _write_text(target_root / "update.txt", "old")
    _write_text(target_root / "target_only.txt", "leftover")

    _write_mirror_map(map_path, source_root=source_root, target_root=target_root)

    out = StringIO()
    err = StringIO()

    exit_code = run_sync(
        root=None,
        map_path=str(map_path),
        output_format="text",
        apply=False,
        yes=False,
        include_unchanged=False,
        out=out,
        err=err,
    )

    output = out.getvalue()
    assert exit_code == 0
    assert "summary: create=1 update=1 unchanged=1 target_only=1" in output
    assert "[target-a] create create.txt" in output
    assert "[target-a] update update.txt" in output
    assert "[target-a] target_only target_only.txt" in output
    assert "[target-a] unchanged same.txt" not in output
    assert err.getvalue() == ""


def test_run_sync_json_output_is_machine_readable(tmp_path: Path) -> None:
    """JSON format should emit structured payload with stable count fields."""

    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    map_path = tmp_path / "mirror_map.yaml"

    _write_text(source_root / "a.txt", "A")
    _write_text(target_root / "a.txt", "B")
    _write_mirror_map(map_path, source_root=source_root, target_root=target_root)

    out = StringIO()
    err = StringIO()

    exit_code = run_sync(
        root=None,
        map_path=str(map_path),
        output_format="json",
        apply=False,
        yes=False,
        include_unchanged=True,
        out=out,
        err=err,
    )

    payload = json.loads(out.getvalue())
    assert exit_code == 0
    assert payload["counts"]["update"] == 1
    assert payload["counts"]["create"] == 0
    assert payload["counts"]["target_only"] == 0
    assert payload["actions"][0]["action"] == "update"
    assert err.getvalue() == ""


def test_run_sync_apply_requires_yes_confirmation(tmp_path: Path) -> None:
    """Apply mode should fail fast unless explicit --yes safety gate is set."""

    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    map_path = tmp_path / "mirror_map.yaml"

    source_root.mkdir(parents=True, exist_ok=True)
    target_root.mkdir(parents=True, exist_ok=True)
    _write_mirror_map(map_path, source_root=source_root, target_root=target_root)

    out = StringIO()
    err = StringIO()

    exit_code = run_sync(
        root=None,
        map_path=str(map_path),
        output_format="text",
        apply=True,
        yes=False,
        include_unchanged=False,
        out=out,
        err=err,
    )

    assert exit_code == 2
    assert "requires --yes" in err.getvalue()


def test_run_sync_apply_writes_create_and_update_only(tmp_path: Path) -> None:
    """Apply mode should write create/update actions and skip destructive deletes."""

    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    map_path = tmp_path / "mirror_map.yaml"

    _write_text(source_root / "update.txt", "new-value")
    _write_text(source_root / "create.txt", "create-value")
    _write_text(target_root / "update.txt", "old-value")
    _write_text(target_root / "target_only.txt", "keep")

    _write_mirror_map(map_path, source_root=source_root, target_root=target_root)

    out = StringIO()
    err = StringIO()

    exit_code = run_sync(
        root=None,
        map_path=str(map_path),
        output_format="text",
        apply=True,
        yes=True,
        include_unchanged=False,
        out=out,
        err=err,
    )

    assert exit_code == 0
    assert (target_root / "update.txt").read_text(encoding="utf-8") == "new-value"
    assert (target_root / "create.txt").read_text(encoding="utf-8") == "create-value"
    assert (target_root / "target_only.txt").read_text(encoding="utf-8") == "keep"
    assert "apply-summary: created=1 updated=1 skipped=1" in out.getvalue()
    assert err.getvalue() == ""
