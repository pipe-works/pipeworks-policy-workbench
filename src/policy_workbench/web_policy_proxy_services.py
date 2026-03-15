"""Focused mud-server policy proxy service helpers for web routes.

This module isolates inventory/detail/activation/publish proxy behavior so
``web_services`` can remain an orchestration layer as Phase 2 decomposition
continues.
"""

from __future__ import annotations

from typing import Protocol, cast
from urllib.parse import quote

from .mud_api_runtime import MudApiRuntimeConfig
from .web_models import (
    PolicyActivationScopeResponse,
    PolicyActivationSetResponse,
    PolicyInventoryResponse,
    PolicyObjectDetailResponse,
    PolicyObjectSummaryResponse,
    PolicyPublishRunProxyResponse,
)


class RuntimeConfigResolver(Protocol):
    """Callable contract for runtime config resolution."""

    def __call__(
        self,
        *,
        session_id_override: str | None,
        base_url_override: str | None = None,
    ) -> MudApiRuntimeConfig: ...


class AuthenticatedMudApiFetcher(Protocol):
    """Callable contract for authenticated mud-server API JSON fetches."""

    def __call__(
        self,
        *,
        runtime: MudApiRuntimeConfig,
        method: str,
        path: str,
        query_params: dict[str, str],
        json_payload: dict[str, object] | None = None,
    ) -> dict[str, object]: ...


def build_policy_inventory_payload(
    *,
    policy_type: str | None,
    namespace: str | None,
    status: str | None,
    session_id_override: str | None,
    base_url_override: str | None,
    resolve_runtime_config: RuntimeConfigResolver,
    fetch_mud_api_json: AuthenticatedMudApiFetcher,
) -> PolicyInventoryResponse:
    """Build policy inventory payload from mud-server canonical API."""
    runtime = resolve_runtime_config(
        session_id_override=session_id_override,
        base_url_override=base_url_override,
    )

    query_params: dict[str, str] = {}
    if (policy_type or "").strip():
        query_params["policy_type"] = str(policy_type).strip()
    if (namespace or "").strip():
        query_params["namespace"] = str(namespace).strip()
    if (status or "").strip():
        query_params["status"] = str(status).strip()

    payload = fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path="/api/policies",
        query_params=query_params,
    )
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Mud policy inventory payload must include 'items' list.")

    items: list[PolicyObjectSummaryResponse] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("Mud policy inventory items must be JSON objects.")
        # Validate against the full detail schema first, then project to summary.
        # This keeps inventory rows aligned with canonical object contracts while
        # allowing the UI list view to return only the fields it needs.
        detail = PolicyObjectDetailResponse.model_validate(raw_item)
        items.append(
            PolicyObjectSummaryResponse(
                policy_id=detail.policy_id,
                policy_type=detail.policy_type,
                namespace=detail.namespace,
                policy_key=detail.policy_key,
                variant=detail.variant,
                schema_version=detail.schema_version,
                policy_version=detail.policy_version,
                status=detail.status,
                content_hash=detail.content_hash,
                updated_at=detail.updated_at,
                updated_by=detail.updated_by,
            )
        )

    return PolicyInventoryResponse(
        filters={
            "policy_type": query_params.get("policy_type"),
            "namespace": query_params.get("namespace"),
            "status": query_params.get("status"),
        },
        item_count=len(items),
        items=items,
    )


def build_policy_object_detail_payload(
    *,
    policy_id: str,
    variant: str | None,
    session_id_override: str | None,
    base_url_override: str | None,
    resolve_runtime_config: RuntimeConfigResolver,
    fetch_mud_api_json: AuthenticatedMudApiFetcher,
) -> PolicyObjectDetailResponse:
    """Build detail payload for one policy object variant."""
    runtime = resolve_runtime_config(
        session_id_override=session_id_override,
        base_url_override=base_url_override,
    )
    query_params: dict[str, str] = {}
    if (variant or "").strip():
        query_params["variant"] = str(variant).strip()

    payload = fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        # Policy IDs include ":" and may include "/" in legacy-compatible
        # selectors, so quote the full identifier to keep route parsing stable.
        path=f"/api/policies/{quote(policy_id, safe='')}",
        query_params=query_params,
    )
    return cast(PolicyObjectDetailResponse, PolicyObjectDetailResponse.model_validate(payload))


def build_policy_activation_scope_payload(
    *,
    scope: str,
    effective: bool,
    session_id_override: str | None,
    base_url_override: str | None,
    resolve_runtime_config: RuntimeConfigResolver,
    fetch_mud_api_json: AuthenticatedMudApiFetcher,
) -> PolicyActivationScopeResponse:
    """Build activation-scope payload from mud-server policy activation API."""
    normalized_scope = str(scope or "").strip()
    if not normalized_scope:
        raise ValueError("scope is required.")

    runtime = resolve_runtime_config(
        session_id_override=session_id_override,
        base_url_override=base_url_override,
    )
    payload = fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path="/api/policy-activations",
        query_params={
            # Scope is normalized at the boundary so backend API calls stay
            # deterministic even when UI/query inputs include surrounding
            # whitespace.
            "scope": normalized_scope,
            "effective": "true" if effective else "false",
        },
    )
    return cast(
        PolicyActivationScopeResponse,
        PolicyActivationScopeResponse.model_validate(payload),
    )


def build_policy_publish_run_payload(
    *,
    publish_run_id: int,
    session_id_override: str | None,
    base_url_override: str | None,
    resolve_runtime_config: RuntimeConfigResolver,
    fetch_mud_api_json: AuthenticatedMudApiFetcher,
) -> PolicyPublishRunProxyResponse:
    """Build publish-run payload proxy from mud-server canonical publish API."""
    runtime = resolve_runtime_config(
        session_id_override=session_id_override,
        base_url_override=base_url_override,
    )
    payload = fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path=f"/api/policy-publish/{publish_run_id}",
        query_params={},
    )
    return cast(
        PolicyPublishRunProxyResponse,
        PolicyPublishRunProxyResponse.model_validate(payload),
    )


def build_policy_activation_set_payload(
    *,
    world_id: str,
    client_profile: str | None,
    policy_id: str,
    variant: str,
    activated_by: str | None,
    session_id_override: str | None,
    base_url_override: str | None,
    resolve_runtime_config: RuntimeConfigResolver,
    fetch_mud_api_json: AuthenticatedMudApiFetcher,
) -> PolicyActivationSetResponse:
    """Set one activation pointer through mud-server canonical policy activation API."""
    normalized_world_id = str(world_id or "").strip()
    normalized_policy_id = str(policy_id or "").strip()
    normalized_variant = str(variant or "").strip()
    normalized_client_profile = str(client_profile or "").strip()
    normalized_activated_by = str(activated_by or "").strip()

    if not normalized_world_id:
        raise ValueError("world_id is required.")
    if not normalized_policy_id:
        raise ValueError("policy_id is required.")
    if not normalized_variant:
        raise ValueError("variant is required.")

    runtime = resolve_runtime_config(
        session_id_override=session_id_override,
        base_url_override=base_url_override,
    )
    payload = fetch_mud_api_json(
        runtime=runtime,
        method="POST",
        path="/api/policy-activations",
        query_params={},
        json_payload={
            "world_id": normalized_world_id,
            "client_profile": normalized_client_profile or None,
            "policy_id": normalized_policy_id,
            "variant": normalized_variant,
            "activated_by": normalized_activated_by or None,
        },
    )
    return cast(
        PolicyActivationSetResponse,
        PolicyActivationSetResponse.model_validate(payload),
    )
