"""Pydantic request/response models for policy workbench web APIs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PolicyArtifactResponse(BaseModel):
    """Serializable policy artifact entry shown in the tree browser.

    ``policy_*`` fields represent the Phase 2 policy-object selector metadata.
    ``is_authorable`` indicates whether runtime saves are allowed through
    mud-server APIs for this artifact in the current pilot.
    """

    relative_path: str
    role: str
    has_prompt_text: bool
    policy_type: str | None = None
    namespace: str | None = None
    policy_key: str | None = None
    variant: str | None = None
    is_authorable: bool = False


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


class RuntimeModeOptionResponse(BaseModel):
    """One source-mode option available to the workbench UI."""

    mode_key: str
    label: str
    source_kind: str
    default_server_url: str | None
    active_server_url: str | None
    url_editable: bool


class RuntimeModeResponse(BaseModel):
    """Current runtime source mode and all selectable mode options."""

    mode_key: str
    source_kind: str
    active_server_url: str | None
    options: list[RuntimeModeOptionResponse]


class RuntimeModeRequest(BaseModel):
    """Request payload to switch runtime source mode."""

    mode_key: str = Field(min_length=1)
    server_url: str | None = None


class RuntimeAuthResponse(BaseModel):
    """Runtime auth/capability probe result for server-backed policy operations.

    ``access_granted`` is ``True`` only when the active session can call
    mud-server policy APIs, which are restricted to admin/superuser roles.
    """

    mode_key: str
    source_kind: str
    active_server_url: str | None
    session_present: bool
    access_granted: bool
    status: str
    detail: str
    available_worlds: list[dict[str, Any]] = Field(default_factory=list)


class RuntimeLoginRequest(BaseModel):
    """Request payload to authenticate against active mud-server profile."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RuntimeLoginResponse(BaseModel):
    """Runtime login result used by workbench session bootstrap controls."""

    success: bool
    session_id: str | None = None
    role: str | None = None
    available_worlds: list[dict[str, Any]] = Field(default_factory=list)
    detail: str


class RuntimeLogoutResponse(BaseModel):
    """Runtime logout result for browser-session teardown."""

    success: bool
    detail: str


class PolicyTypeOptionsResponse(BaseModel):
    """Canonical policy-type options for inventory filtering."""

    items: list[str]
    source: str
    detail: str | None = None


class PolicySaveRequest(BaseModel):
    """Request payload for Phase 2 API-only policy save operations."""

    policy_type: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    policy_key: str = Field(min_length=1)
    variant: str = Field(min_length=1)
    raw_content: str
    schema_version: str = Field(default="1.0", min_length=1)
    status: str = Field(default="draft", min_length=1)
    activate: bool = False
    world_id: str | None = None
    client_profile: str | None = None
    actor: str | None = None
    session_id: str | None = None


class PolicySaveResponse(BaseModel):
    """Response payload for Phase 2 API-only policy save operations."""

    policy_id: str
    variant: str
    policy_version: int
    content_hash: str
    validation_run_id: int
    activated: bool
    activation_audit_event_id: int | None


class PolicyValidateRequest(BaseModel):
    """Request payload for validate-only policy object checks."""

    policy_type: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    policy_key: str = Field(min_length=1)
    variant: str = Field(min_length=1)
    raw_content: str
    schema_version: str = Field(default="1.0", min_length=1)
    status: str = Field(default="draft", min_length=1)
    actor: str | None = None
    session_id: str | None = None


class PolicyValidateResponse(BaseModel):
    """Response payload for validate-only policy object checks."""

    policy_id: str
    variant: str
    policy_version: int
    validation_run_id: int
    is_valid: bool


class PolicyObjectSummaryResponse(BaseModel):
    """Summary row for API-first policy inventory listing."""

    policy_id: str
    policy_type: str
    namespace: str
    policy_key: str
    variant: str
    schema_version: str
    policy_version: int
    status: str
    content_hash: str
    updated_at: str
    updated_by: str


class PolicyObjectDetailResponse(PolicyObjectSummaryResponse):
    """Detailed policy object payload including canonical content."""

    content: dict[str, Any]


class PolicyInventoryResponse(BaseModel):
    """API-first inventory payload for policy object browsing."""

    filters: dict[str, str | None]
    item_count: int
    items: list[PolicyObjectSummaryResponse]


class PolicyActivationScopeResponse(BaseModel):
    """Activation mapping payload returned from mud-server proxy route."""

    world_id: str
    client_profile: str | None
    items: list[dict[str, Any]]


class PolicyActivationSetRequest(BaseModel):
    """Request payload for one activation pointer mutation."""

    world_id: str = Field(min_length=1)
    client_profile: str | None = None
    policy_id: str = Field(min_length=1)
    variant: str = Field(min_length=1)
    activated_by: str | None = None
    session_id: str | None = None


class PolicyActivationSetResponse(BaseModel):
    """Response payload for one activation pointer mutation."""

    world_id: str
    client_profile: str | None
    policy_id: str
    variant: str
    activated_at: str
    activated_by: str
    rollback_of_activation_id: int | None
    audit_event_id: int | None = None


class PolicyPublishRunProxyResponse(BaseModel):
    """Publish-run payload returned from mud-server proxy route."""

    publish_run_id: int
    world_id: str
    client_profile: str | None
    actor: str
    created_at: str
    manifest: dict[str, Any]
    artifact: dict[str, Any]


class HashDirectoryResponse(BaseModel):
    """One directory hash summary from canonical policy snapshot payload."""

    path: str
    file_count: int
    hash: str


class HashCanonicalResponse(BaseModel):
    """Canonical mud-server hash snapshot metadata used by Step 1 UI."""

    hash_version: str
    canonical_root: str
    generated_at: str
    file_count: int
    root_hash: str
    directories: list[HashDirectoryResponse]
