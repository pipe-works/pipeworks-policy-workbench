"""Unit tests for extracted policy proxy web service helpers."""

from __future__ import annotations

import pytest

from policy_workbench import web_policy_proxy_services
from policy_workbench.mud_api_runtime import MudApiRuntimeConfig


def test_build_policy_inventory_payload_filters_and_serializes_items() -> None:
    """Inventory helper should normalize filters and serialize summary rows."""
    captured: dict[str, object] = {}

    def _fake_fetch(*, runtime, method, path, query_params):  # noqa: ANN001
        captured["runtime"] = runtime
        captured["method"] = method
        captured["path"] = path
        captured["query_params"] = query_params
        return {
            "items": [
                {
                    "policy_id": "species_block:image.blocks.species:goblin",
                    "policy_type": "species_block",
                    "namespace": "image.blocks.species",
                    "policy_key": "goblin",
                    "variant": "v1",
                    "schema_version": "1.0",
                    "policy_version": 4,
                    "status": "draft",
                    "content": {"text": "Goblin text"},
                    "content_hash": "hash-1",
                    "updated_at": "2026-03-11T21:00:00Z",
                    "updated_by": "tester",
                }
            ]
        }

    payload = web_policy_proxy_services.build_policy_inventory_payload(
        policy_type=" species_block ",
        namespace=" image.blocks.species ",
        status=" draft ",
        session_id_override="session-1",
        base_url_override="https://dev.mud.example:9443",
        resolve_runtime_config=lambda **_kwargs: MudApiRuntimeConfig(
            base_url="https://dev.mud.example:9443",
            session_id="session-1",
        ),
        fetch_mud_api_json=_fake_fetch,
    )
    assert payload.item_count == 1
    assert payload.items[0].policy_id == "species_block:image.blocks.species:goblin"
    assert payload.filters == {
        "policy_type": "species_block",
        "namespace": "image.blocks.species",
        "status": "draft",
    }
    assert captured["method"] == "GET"
    assert captured["path"] == "/api/policies"
    assert captured["query_params"] == {
        "policy_type": "species_block",
        "namespace": "image.blocks.species",
        "status": "draft",
    }


def test_build_policy_inventory_payload_rejects_invalid_item_shapes() -> None:
    """Inventory helper should reject malformed mud-server payload contracts."""
    with pytest.raises(ValueError, match="must include 'items' list"):
        web_policy_proxy_services.build_policy_inventory_payload(
            policy_type=None,
            namespace=None,
            status=None,
            session_id_override="session-1",
            base_url_override=None,
            resolve_runtime_config=lambda **_kwargs: MudApiRuntimeConfig(
                base_url="http://mud.local:8000",
                session_id="session-1",
            ),
            fetch_mud_api_json=lambda **_kwargs: {"items": "bad"},
        )

    with pytest.raises(ValueError, match="must be JSON objects"):
        web_policy_proxy_services.build_policy_inventory_payload(
            policy_type=None,
            namespace=None,
            status=None,
            session_id_override="session-1",
            base_url_override=None,
            resolve_runtime_config=lambda **_kwargs: MudApiRuntimeConfig(
                base_url="http://mud.local:8000",
                session_id="session-1",
            ),
            fetch_mud_api_json=lambda **_kwargs: {"items": [7]},
        )


def test_detail_activation_publish_builders_call_expected_routes() -> None:
    """Detail/activation/publish helpers should call expected mud API routes."""
    captured_calls: list[dict[str, object]] = []

    def _fake_fetch(*, runtime, method, path, query_params):  # noqa: ANN001
        captured_calls.append(
            {
                "runtime": runtime,
                "method": method,
                "path": path,
                "query_params": query_params,
            }
        )
        if path.startswith("/api/policies/"):
            return {
                "policy_id": "species_block:image.blocks.species:goblin",
                "policy_type": "species_block",
                "namespace": "image.blocks.species",
                "policy_key": "goblin",
                "variant": "v1",
                "schema_version": "1.0",
                "policy_version": 4,
                "status": "draft",
                "content": {"text": "Goblin text"},
                "content_hash": "hash-1",
                "updated_at": "2026-03-11T21:00:00Z",
                "updated_by": "tester",
            }
        if path == "/api/policy-activations":
            return {
                "world_id": "pipeworks_web",
                "client_profile": "mobile",
                "items": [
                    {
                        "world_id": "pipeworks_web",
                        "client_profile": "mobile",
                        "policy_id": "species_block:image.blocks.species:goblin",
                        "variant": "v1",
                    }
                ],
            }
        if path.startswith("/api/policy-publish/"):
            return {
                "publish_run_id": 9,
                "world_id": "pipeworks_web",
                "client_profile": "mobile",
                "actor": "tester",
                "created_at": "2026-03-11T21:00:00Z",
                "manifest": {"manifest_hash": "mhash"},
                "artifact": {"artifact_hash": "ahash", "artifact_path": "/tmp/export.json"},
            }
        raise AssertionError(f"Unexpected route: {path}")

    resolver = lambda **_kwargs: MudApiRuntimeConfig(  # noqa: E731
        base_url="http://mud.local:8000",
        session_id="session-1",
    )

    detail_payload = web_policy_proxy_services.build_policy_object_detail_payload(
        policy_id="species_block:image.blocks.species:goblin/v1",
        variant=" v1 ",
        session_id_override="session-1",
        base_url_override=None,
        resolve_runtime_config=resolver,
        fetch_mud_api_json=_fake_fetch,
    )
    assert detail_payload.variant == "v1"

    activation_payload = web_policy_proxy_services.build_policy_activation_scope_payload(
        scope=" pipeworks_web:mobile ",
        effective=False,
        session_id_override="session-1",
        base_url_override=None,
        resolve_runtime_config=resolver,
        fetch_mud_api_json=_fake_fetch,
    )
    assert activation_payload.world_id == "pipeworks_web"
    assert activation_payload.items[0]["policy_id"] == "species_block:image.blocks.species:goblin"

    publish_payload = web_policy_proxy_services.build_policy_publish_run_payload(
        publish_run_id=9,
        session_id_override="session-1",
        base_url_override=None,
        resolve_runtime_config=resolver,
        fetch_mud_api_json=_fake_fetch,
    )
    assert publish_payload.publish_run_id == 9

    assert (
        captured_calls[0]["path"]
        == "/api/policies/species_block%3Aimage.blocks.species%3Agoblin%2Fv1"
    )
    assert captured_calls[0]["query_params"] == {"variant": "v1"}
    assert captured_calls[1]["path"] == "/api/policy-activations"
    assert captured_calls[1]["query_params"] == {
        "scope": "pipeworks_web:mobile",
        "effective": "false",
    }
    assert captured_calls[2]["path"] == "/api/policy-publish/9"
    assert captured_calls[2]["query_params"] == {}


def test_build_policy_activation_scope_payload_rejects_blank_scope() -> None:
    """Activation helper should fail fast when scope is blank after trimming."""

    with pytest.raises(ValueError, match="scope is required"):
        web_policy_proxy_services.build_policy_activation_scope_payload(
            scope="   ",
            effective=True,
            session_id_override="session-1",
            base_url_override=None,
            resolve_runtime_config=lambda **_kwargs: MudApiRuntimeConfig(
                base_url="http://mud.local:8000",
                session_id="session-1",
            ),
            fetch_mud_api_json=lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("fetch_mud_api_json should not be called for blank scope")
            ),
        )
