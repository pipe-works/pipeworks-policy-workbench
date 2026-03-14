"""Shared mud-server API runtime configuration helpers.

This module centralizes base URL and session-id resolution semantics so
API-facing modules can share one deterministic validation path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MudApiRuntimeConfig:
    """Resolved mud-server API runtime configuration."""

    base_url: str
    session_id: str
    timeout_seconds: float = 8.0


def resolve_mud_api_runtime_config(
    *,
    session_id_override: str | None,
    base_url_override: str | None,
    base_url_env_var: str,
    session_id_env_var: str,
    default_base_url: str,
    empty_base_url_error: str,
    missing_session_error: str,
    timeout_seconds: float = 8.0,
) -> MudApiRuntimeConfig:
    """Resolve and validate runtime config from overrides + environment values."""

    base_candidate = (
        base_url_override
        if base_url_override is not None
        else os.getenv(base_url_env_var, default_base_url)
    )
    base_url = (base_candidate or "").strip().rstrip("/")
    if not base_url:
        raise ValueError(empty_base_url_error)

    session_candidate = (
        session_id_override
        if session_id_override is not None
        else os.getenv(session_id_env_var, "")
    )
    session_id = (session_candidate or "").strip()
    if not session_id:
        raise ValueError(missing_session_error)

    return MudApiRuntimeConfig(
        base_url=base_url,
        session_id=session_id,
        timeout_seconds=timeout_seconds,
    )
