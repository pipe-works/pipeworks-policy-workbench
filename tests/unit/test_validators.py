"""Unit tests for snapshot validation rules."""

from __future__ import annotations

from pathlib import Path

from policy_workbench.models import (
    IssueLevel,
    PolicyArtifact,
    PolicyFileRole,
    PolicyTreeSnapshot,
)
from policy_workbench.validators import validate_snapshot


def test_validate_snapshot_flags_prompt_without_text() -> None:
    """Prompt-bearing artifacts must include extracted prompt content."""

    snapshot = PolicyTreeSnapshot(
        root=Path("/tmp/policies"),
        directories=["policies"],
        artifacts=[
            PolicyArtifact(
                absolute_path=Path("/tmp/policies/image/blocks/species/goblin_v1.yaml"),
                relative_path="image/blocks/species/goblin_v1.yaml",
                role=PolicyFileRole.PROMPT_YAML,
                prompt_text="",
            )
        ],
    )

    report = validate_snapshot(snapshot)

    assert report.has_errors is True
    assert any(issue.code == "PROMPT_TEXT_MISSING" for issue in report.issues)


def test_validate_snapshot_flags_unknown_role_and_empty_prompt_set() -> None:
    """Unknown files and missing prompt artifacts should be visible as warnings."""

    snapshot = PolicyTreeSnapshot(
        root=Path("/tmp/policies"),
        directories=["policies"],
        artifacts=[
            PolicyArtifact(
                absolute_path=Path("/tmp/policies/other.bin"),
                relative_path="other.bin",
                role=PolicyFileRole.UNKNOWN,
            )
        ],
    )

    report = validate_snapshot(snapshot)

    warning_codes = {issue.code for issue in report.issues if issue.level == IssueLevel.WARNING}
    assert "UNKNOWN_ROLE" in warning_codes
    assert "NO_PROMPT_ARTIFACTS" in warning_codes


def test_validate_snapshot_surfaces_duplicate_paths() -> None:
    """Duplicate relative paths should be treated as validation errors."""

    duplicate_path = "image/prompts/portrait.txt"
    snapshot = PolicyTreeSnapshot(
        root=Path("/tmp/policies"),
        directories=["policies"],
        artifacts=[
            PolicyArtifact(
                absolute_path=Path("/tmp/policies/image/prompts/portrait.txt"),
                relative_path=duplicate_path,
                role=PolicyFileRole.PROMPT_TEXT,
                prompt_text="One",
            ),
            PolicyArtifact(
                absolute_path=Path("/tmp/policies/image/prompts/portrait_copy.txt"),
                relative_path=duplicate_path,
                role=PolicyFileRole.PROMPT_TEXT,
                prompt_text="Two",
            ),
        ],
    )

    report = validate_snapshot(snapshot)

    duplicate_issues = [issue for issue in report.issues if issue.code == "DUPLICATE_PATH"]
    assert len(duplicate_issues) == 1
    assert duplicate_issues[0].relative_path == duplicate_path


def test_validate_snapshot_maps_artifact_notes_to_levels() -> None:
    """Scanner notes should map to expected severity levels."""

    snapshot = PolicyTreeSnapshot(
        root=Path("/tmp/policies"),
        directories=["policies"],
        artifacts=[
            PolicyArtifact(
                absolute_path=Path("/tmp/policies/image/prompts/portrait.txt"),
                relative_path="image/prompts/portrait.txt",
                role=PolicyFileRole.PROMPT_TEXT,
                prompt_text="portrait",
                notes=["prompt text file is empty", "some informational note"],
            )
        ],
    )

    report = validate_snapshot(snapshot)

    codes_by_level = {(issue.code, issue.level) for issue in report.issues}
    assert ("ARTIFACT_CONTENT_WARNING", IssueLevel.WARNING) in codes_by_level
    assert ("ARTIFACT_NOTE", IssueLevel.INFO) in codes_by_level
