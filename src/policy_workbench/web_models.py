"""Pydantic request/response models for policy workbench web APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PolicyArtifactResponse(BaseModel):
    """Serializable policy artifact entry shown in the tree browser."""

    relative_path: str
    role: str
    has_prompt_text: bool


class PolicyTreeResponse(BaseModel):
    """Top-level payload for canonical policy tree listing."""

    source_root: str
    directories: list[str]
    artifacts: list[PolicyArtifactResponse]


class PolicyFileResponse(BaseModel):
    """Payload returned when loading one policy file."""

    source_root: str
    relative_path: str
    content: str


class PolicyFileUpdateRequest(BaseModel):
    """Request payload for saving one policy file."""

    relative_path: str = Field(min_length=1)
    content: str


class PolicyFileUpdateResponse(BaseModel):
    """Response payload for file save operations."""

    source_root: str
    relative_path: str
    bytes_written: int


class ValidationIssueResponse(BaseModel):
    """Serializable validation issue entry."""

    level: str
    code: str
    message: str
    relative_path: str | None = None


class ValidationResponse(BaseModel):
    """Validation summary payload returned to the web UI."""

    source_root: str
    counts: dict[str, int]
    issues: list[ValidationIssueResponse]


class SyncActionResponse(BaseModel):
    """Serializable sync action row for dry-run/apply previews."""

    target: str
    relative_path: str
    action: str
    source_path: str | None
    target_path: str | None
    reason: str | None = None


class SyncPlanResponse(BaseModel):
    """Sync plan payload used by the impact panel in the web UI."""

    source_root: str
    map_path: str
    counts: dict[str, int]
    actions: list[SyncActionResponse]


class SyncApplyRequest(BaseModel):
    """Request payload for sync apply endpoint safety gate."""

    confirm: bool = False


class SyncApplyResponse(BaseModel):
    """Result payload for apply-mode execution from the web UI."""

    created: int
    updated: int
    skipped: int
