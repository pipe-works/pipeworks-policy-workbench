"""Core domain models for policy scanning and validation.

The workbench uses these models to pass structured data between modules without
leaking implementation details (for example raw parser internals) into command
handlers or future API routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class PolicyFileRole(StrEnum):
    """Semantic role for one policy file.

    Role values are intentionally explicit so validation logic can apply
    role-specific rules deterministically.
    """

    PROMPT_TEXT = "prompt_text"
    PROMPT_YAML = "prompt_yaml"
    REGISTRY_YAML = "registry_yaml"
    AXIS_POLICY_YAML = "axis_policy_yaml"
    MANIFEST_YAML = "manifest_yaml"
    TONE_PROFILE_JSON = "tone_profile_json"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class PolicyArtifact:
    """One discovered file inside a scanned canonical policy tree."""

    absolute_path: Path
    relative_path: str
    role: PolicyFileRole
    prompt_text: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PolicyTreeSnapshot:
    """In-memory representation of the scanned policy tree."""

    root: Path
    directories: list[str]
    artifacts: list[PolicyArtifact]

    def artifacts_for_role(self, role: PolicyFileRole) -> list[PolicyArtifact]:
        """Return all artifacts matching ``role``.

        This helper keeps command code compact and avoids re-implementing common
        filtering logic across multiple call sites.
        """

        return [artifact for artifact in self.artifacts if artifact.role == role]


class IssueLevel(StrEnum):
    """Severity bucket for validation issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True)
class ValidationIssue:
    """One validation issue raised against a specific artifact."""

    level: IssueLevel
    code: str
    message: str
    relative_path: str | None = None


@dataclass(slots=True)
class ValidationReport:
    """Structured validation result for a full policy tree."""

    root: Path
    issues: list[ValidationIssue]

    @property
    def has_errors(self) -> bool:
        """Return ``True`` when at least one error-level issue exists."""

        return any(issue.level == IssueLevel.ERROR for issue in self.issues)

    def count(self, level: IssueLevel) -> int:
        """Count issues at a given severity ``level``."""

        return sum(1 for issue in self.issues if issue.level == level)
