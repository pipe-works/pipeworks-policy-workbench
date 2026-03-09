"""Validation rules for scanned policy artifacts.

Validation runs against the deterministic ``PolicyTreeSnapshot`` produced by the
scanner. Rules in this module are intentionally explicit and conservative so
operators can trust failures as actionable signals.
"""

from __future__ import annotations

from collections import Counter

from .models import (
    IssueLevel,
    PolicyArtifact,
    PolicyFileRole,
    PolicyTreeSnapshot,
    ValidationIssue,
    ValidationReport,
)


def validate_snapshot(snapshot: PolicyTreeSnapshot) -> ValidationReport:
    """Evaluate a tree snapshot and return a structured validation report.

    Current rule set:
    - unknown artifact roles are reported as warnings
    - prompt-bearing artifacts must expose non-empty extracted prompt text
    - duplicate relative paths are reported as errors
    - scanner notes are surfaced as warnings/errors depending on severity
    - lack of prompt-bearing artifacts is reported as a warning
    """

    issues: list[ValidationIssue] = []

    issues.extend(_validate_duplicate_relative_paths(snapshot.artifacts))

    prompt_artifact_count = 0
    for artifact in snapshot.artifacts:
        issues.extend(_issues_from_artifact_notes(artifact))

        if artifact.role == PolicyFileRole.UNKNOWN:
            issues.append(
                ValidationIssue(
                    level=IssueLevel.WARNING,
                    code="UNKNOWN_ROLE",
                    message="artifact could not be classified",
                    relative_path=artifact.relative_path,
                )
            )

        if artifact.role in {PolicyFileRole.PROMPT_TEXT, PolicyFileRole.PROMPT_YAML}:
            prompt_artifact_count += 1
            if not (artifact.prompt_text or "").strip():
                issues.append(
                    ValidationIssue(
                        level=IssueLevel.ERROR,
                        code="PROMPT_TEXT_MISSING",
                        message="prompt-bearing artifact has no usable prompt text",
                        relative_path=artifact.relative_path,
                    )
                )

    if prompt_artifact_count == 0:
        issues.append(
            ValidationIssue(
                level=IssueLevel.WARNING,
                code="NO_PROMPT_ARTIFACTS",
                message="no prompt-bearing artifacts discovered",
                relative_path=None,
            )
        )

    return ValidationReport(root=snapshot.root, issues=issues)


def _validate_duplicate_relative_paths(artifacts: list[PolicyArtifact]) -> list[ValidationIssue]:
    """Return errors for duplicate relative paths within a snapshot."""

    counts = Counter(artifact.relative_path for artifact in artifacts)
    duplicates = sorted(path for path, count in counts.items() if count > 1)

    return [
        ValidationIssue(
            level=IssueLevel.ERROR,
            code="DUPLICATE_PATH",
            message="duplicate relative path encountered in scanner output",
            relative_path=duplicate,
        )
        for duplicate in duplicates
    ]


def _issues_from_artifact_notes(artifact: PolicyArtifact) -> list[ValidationIssue]:
    """Translate scanner notes into validation issues with severity mapping."""

    issues: list[ValidationIssue] = []
    for note in artifact.notes:
        normalized = note.lower()
        if "read failed" in normalized or "not utf-8" in normalized:
            level = IssueLevel.ERROR
            code = "ARTIFACT_READ_ERROR"
        elif "missing usable text" in normalized or "is empty" in normalized:
            level = IssueLevel.WARNING
            code = "ARTIFACT_CONTENT_WARNING"
        else:
            level = IssueLevel.INFO
            code = "ARTIFACT_NOTE"

        issues.append(
            ValidationIssue(
                level=level,
                code=code,
                message=note,
                relative_path=artifact.relative_path,
            )
        )

    return issues
