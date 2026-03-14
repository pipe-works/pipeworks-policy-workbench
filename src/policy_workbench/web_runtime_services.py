"""Focused runtime/auth policy service helpers for web routes.

This module isolates runtime session/auth probing plus policy option loading so
``web_services`` can stay orchestration-focused during Phase 2 refactoring.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .mud_api_runtime import MudApiRuntimeConfig
from .web_models import PolicyTypeOptionsResponse, RuntimeAuthResponse, RuntimeLoginResponse


class AuthenticatedMudApiFetcher(Protocol):
    """Callable contract for authenticated mud-server API JSON fetches."""

    def __call__(
        self,
        *,
        runtime: MudApiRuntimeConfig,
        method: str,
        path: str,
        query_params: dict[str, str],
    ) -> dict[str, object]: ...


class AnonymousMudApiFetcher(Protocol):
    """Callable contract for anonymous mud-server API JSON fetches."""

    def __call__(
        self,
        *,
        base_url: str,
        method: str,
        path: str,
        body: dict[str, object] | None,
        timeout_seconds: float = 8.0,
    ) -> dict[str, object]: ...


class RuntimeConfigResolver(Protocol):
    """Callable contract for runtime config resolution."""

    def __call__(
        self,
        *,
        session_id_override: str | None,
        base_url_override: str | None = None,
    ) -> MudApiRuntimeConfig: ...


class PolicyCapabilitiesFetcher(Protocol):
    """Callable contract for capabilities payload fetch helpers."""

    def __call__(
        self,
        *,
        runtime: MudApiRuntimeConfig,
    ) -> dict[str, object]: ...


def build_runtime_auth_payload(
    *,
    mode_key: str,
    source_kind: str,
    active_server_url: str | None,
    session_id_override: str | None,
    base_url_override: str | None,
    resolve_runtime_config: RuntimeConfigResolver,
    fetch_policy_capabilities: PolicyCapabilitiesFetcher,
    classify_runtime_probe_error: Callable[[str], tuple[str, str]],
) -> RuntimeAuthResponse:
    """Build runtime auth/capability payload for server-backed operations."""

    if source_kind != "server_api":
        return RuntimeAuthResponse(
            mode_key=mode_key,
            source_kind=source_kind,
            active_server_url=active_server_url,
            session_present=False,
            access_granted=False,
            status="error",
            detail="Runtime mode must be server_api.",
        )

    try:
        runtime = resolve_runtime_config(
            session_id_override=session_id_override,
            base_url_override=base_url_override,
        )
    except ValueError:
        # Treat missing/invalid runtime config as "missing_session" so the UI
        # can present a recovery action (login) instead of a generic error.
        return RuntimeAuthResponse(
            mode_key=mode_key,
            source_kind=source_kind,
            active_server_url=active_server_url,
            session_present=False,
            access_granted=False,
            status="missing_session",
            detail="No active runtime session. Login with an admin/superuser account.",
        )

    try:
        fetch_policy_capabilities(runtime=runtime)
    except ValueError as exc:
        status, detail = classify_runtime_probe_error(str(exc))
        return RuntimeAuthResponse(
            mode_key=mode_key,
            source_kind=source_kind,
            active_server_url=runtime.base_url,
            session_present=True,
            access_granted=False,
            status=status,
            detail=detail,
        )

    return RuntimeAuthResponse(
        mode_key=mode_key,
        source_kind=source_kind,
        active_server_url=runtime.base_url,
        session_present=True,
        access_granted=True,
        status="authorized",
        detail="Session is authorized for admin/superuser policy APIs.",
    )


def build_runtime_login_payload(
    *,
    mode_key: str,
    source_kind: str,
    active_server_url: str | None,
    username: str,
    password: str,
    base_url_override: str | None,
    default_base_url: str,
    allowed_roles: set[str],
    normalize_base_url: Callable[[str | None], str],
    fetch_mud_api_json_anonymous: AnonymousMudApiFetcher,
) -> RuntimeLoginResponse:
    """Authenticate against mud-server and return normalized session details."""
    if source_kind != "server_api":
        raise ValueError("Runtime mode must be server_api.")

    normalized_username = (username or "").strip()
    if not normalized_username:
        raise ValueError("Username is required.")
    normalized_password = (password or "").strip()
    if not normalized_password:
        raise ValueError("Password is required.")

    runtime_base_url = (
        base_url_override
        if base_url_override is not None
        else active_server_url if active_server_url is not None else default_base_url
    )
    base_url = normalize_base_url(runtime_base_url)
    if not base_url:
        raise ValueError("Mud API base URL must not be empty.")

    payload = fetch_mud_api_json_anonymous(
        base_url=base_url,
        method="POST",
        path="/login",
        body={
            "username": normalized_username,
            "password": normalized_password,
        },
    )

    session_id = payload.get("session_id")
    role = payload.get("role")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Mud login response did not include session_id.")
    if not isinstance(role, str) or not role.strip():
        raise ValueError("Mud login response did not include role.")
    normalized_role = role.strip()
    if normalized_role not in allowed_roles:
        # Login itself succeeded, but policy APIs are role-gated. Returning
        # success=False with session metadata lets operators see who they are
        # authenticated as without incorrectly marking policy access as allowed.
        return RuntimeLoginResponse(
            success=False,
            session_id=session_id.strip(),
            role=normalized_role,
            detail="Authenticated, but role is not admin/superuser for policy APIs.",
        )

    return RuntimeLoginResponse(
        success=True,
        session_id=session_id.strip(),
        role=normalized_role,
        detail="Authenticated as admin/superuser.",
    )


def build_policy_type_options_payload(
    *,
    source_kind: str,
    active_server_url: str | None,
    session_id_override: str | None,
    base_url_override: str | None,
    resolve_runtime_config: RuntimeConfigResolver,
    fetch_policy_capabilities: PolicyCapabilitiesFetcher,
) -> PolicyTypeOptionsResponse:
    """Return canonical policy-type options from mud-server capabilities."""
    if source_kind != "server_api":
        raise ValueError("Runtime mode must be server_api.")
    runtime = resolve_runtime_config(
        session_id_override=session_id_override,
        base_url_override=(
            base_url_override if base_url_override is not None else active_server_url
        ),
    )
    payload = fetch_policy_capabilities(runtime=runtime)
    api_policy_types = extract_string_list_from_capabilities_payload(
        payload=payload,
        field_name="allowed_policy_types",
    )
    return PolicyTypeOptionsResponse(
        items=api_policy_types,
        source="mud_server_api",
        detail="Policy types resolved from mud-server policy capabilities.",
    )


def build_policy_namespace_options_payload(
    *,
    source_kind: str,
    active_server_url: str | None,
    session_id_override: str | None,
    policy_type: str | None,
    base_url_override: str | None,
    resolve_runtime_config: RuntimeConfigResolver,
    fetch_mud_api_json: AuthenticatedMudApiFetcher,
) -> PolicyTypeOptionsResponse:
    """Return canonical policy namespace options from mud-server inventory."""
    if source_kind != "server_api":
        raise ValueError("Runtime mode must be server_api.")
    normalized_policy_type = str(policy_type or "").strip() or None
    runtime = resolve_runtime_config(
        session_id_override=session_id_override,
        base_url_override=(
            base_url_override if base_url_override is not None else active_server_url
        ),
    )
    query_params: dict[str, str] = {}
    if normalized_policy_type:
        query_params["policy_type"] = normalized_policy_type
    payload = fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path="/api/policies",
        query_params=query_params,
    )
    api_namespaces = extract_namespaces_from_inventory_payload(payload)
    return PolicyTypeOptionsResponse(
        items=api_namespaces,
        source="mud_server_api",
        detail="Namespaces resolved from mud-server API inventory.",
    )


def build_policy_status_options_payload(
    *,
    source_kind: str,
    active_server_url: str | None,
    session_id_override: str | None,
    base_url_override: str | None,
    resolve_runtime_config: RuntimeConfigResolver,
    fetch_policy_capabilities: PolicyCapabilitiesFetcher,
) -> PolicyTypeOptionsResponse:
    """Return canonical policy status options from mud-server capabilities."""
    if source_kind != "server_api":
        raise ValueError("Runtime mode must be server_api.")
    runtime = resolve_runtime_config(
        session_id_override=session_id_override,
        base_url_override=(
            base_url_override if base_url_override is not None else active_server_url
        ),
    )
    payload = fetch_policy_capabilities(runtime=runtime)
    statuses = extract_string_list_from_capabilities_payload(
        payload=payload,
        field_name="allowed_statuses",
    )
    return PolicyTypeOptionsResponse(
        items=statuses,
        source="mud_server_api",
        detail="Statuses resolved from mud-server policy capabilities.",
    )


def classify_runtime_auth_probe_error(
    *,
    error_detail: str,
    role_required_detail: str,
) -> tuple[str, str]:
    """Classify capability probe failures into stable UI-facing status codes."""
    # Use explicit phrase checks here to decouple UI auth-state transitions
    # from backend HTTP/status formatting details.
    if role_required_detail in error_detail:
        return (
            "forbidden",
            "Session is valid but role is not admin/superuser.",
        )

    if "Invalid or expired session" in error_detail or "Invalid session user" in error_detail:
        return (
            "unauthenticated",
            "Session is invalid or expired.",
        )

    return ("error", error_detail)


def fetch_policy_capabilities_payload(
    *,
    runtime: MudApiRuntimeConfig,
    fetch_mud_api_json: AuthenticatedMudApiFetcher,
) -> dict[str, object]:
    """Fetch and validate mud-server policy capabilities payload."""
    payload = fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path="/api/policy-capabilities",
        query_params={},
    )
    _ = extract_string_list_from_capabilities_payload(
        payload=payload,
        field_name="allowed_policy_types",
    )
    _ = extract_string_list_from_capabilities_payload(
        payload=payload,
        field_name="allowed_statuses",
    )
    return payload


def extract_string_list_from_capabilities_payload(
    *,
    payload: dict[str, object],
    field_name: str,
) -> list[str]:
    """Extract and normalize one string-list field from capabilities payload."""
    raw_values = payload.get(field_name)
    if not isinstance(raw_values, list):
        raise ValueError(f"Mud API /api/policy-capabilities response must include {field_name!r}.")

    values: list[str] = []
    for value in raw_values:
        normalized = str(value or "").strip()
        if normalized:
            values.append(normalized)
    return dedupe_preserve_order(values)


def extract_namespaces_from_inventory_payload(payload: dict[str, object]) -> list[str]:
    """Extract stable namespace list from ``GET /api/policies`` payload."""
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Mud API /api/policies response must include an 'items' list.")

    namespaces: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        namespace = str(item.get("namespace", "")).strip()
        if namespace:
            namespaces.append(namespace)
    return dedupe_preserve_order(namespaces)


def dedupe_preserve_order(values: list[str]) -> list[str]:
    """Normalize duplicate-prone lists while preserving first-seen ordering."""
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique
