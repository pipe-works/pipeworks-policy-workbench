"""Unit tests for shared mud API HTTP transport helpers."""

from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

from policy_workbench import mud_api_client
from policy_workbench.mud_api_runtime import MudApiRuntimeConfig


class _FakeHttpResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def test_normalize_base_url_trims_and_handles_empty_values() -> None:
    """Base URL normalization should trim whitespace and one trailing slash."""
    assert (
        mud_api_client.normalize_base_url(" https://mud.local:8000/ ") == "https://mud.local:8000"
    )
    assert mud_api_client.normalize_base_url("   ") == ""
    assert mud_api_client.normalize_base_url(None) == ""


def test_mud_api_http_error_detail_prefers_contract_payload_fields() -> None:
    """HTTP detail helper should prefer payload code/detail over generic status."""
    contract_payload = b'{"code":"POLICY_VALIDATION_ERROR","detail":"invalid"}'
    assert (
        mud_api_client.mud_api_http_error_detail(
            SimpleNamespace(code=422, read=lambda: contract_payload)
        )
        == "POLICY_VALIDATION_ERROR: invalid"
    )
    assert (
        mud_api_client.mud_api_http_error_detail(
            SimpleNamespace(code=422, read=lambda: b'{"detail":"plain detail"}')
        )
        == "plain detail"
    )
    assert (
        mud_api_client.mud_api_http_error_detail(SimpleNamespace(code=422, read=lambda: b"{}"))
        == "HTTP 422"
    )


def test_mud_api_http_error_detail_handles_missing_reader_and_parse_failures() -> None:
    """HTTP detail helper should safely fallback when payload parsing is unavailable."""

    assert mud_api_client.mud_api_http_error_detail(SimpleNamespace(code=401)) == "HTTP 401"
    assert (
        mud_api_client.mud_api_http_error_detail(
            SimpleNamespace(code=500, read=lambda: (_ for _ in ()).throw(OSError("boom")))
        )
        == "HTTP 500"
    )


def test_request_json_handles_success_not_found_http_and_transport_errors() -> None:
    """Shared request helper should keep stable behavior across key branches."""
    success = mud_api_client.request_json(
        method="GET",
        url="http://mud.local/api/test",
        timeout_seconds=8.0,
        error_prefix="Mud policy API request failed",
        non_object_error_message="non-object",
        opener=lambda request, timeout=8.0: _FakeHttpResponse(b'{"ok": true}'),
    )
    assert success == {"ok": True}

    not_found_error = HTTPError(
        url="http://mud.local/api/test",
        code=404,
        msg="not found",
        hdrs=None,
        fp=BytesIO(b"{}"),
    )
    assert (
        mud_api_client.request_json(
            method="GET",
            url="http://mud.local/api/test",
            timeout_seconds=8.0,
            allow_not_found=True,
            error_prefix="Mud policy API request failed",
            non_object_error_message="non-object",
            opener=lambda *args, **kwargs: (_ for _ in ()).throw(not_found_error),
        )
        is None
    )

    http_error = HTTPError(
        url="http://mud.local/api/test",
        code=422,
        msg="bad request",
        hdrs=None,
        fp=BytesIO(b'{"code":"POLICY_VALIDATION_ERROR","detail":"invalid"}'),
    )
    with pytest.raises(ValueError, match="POLICY_VALIDATION_ERROR: invalid"):
        mud_api_client.request_json(
            method="POST",
            url="http://mud.local/api/test",
            timeout_seconds=8.0,
            error_prefix="Mud policy API request failed",
            non_object_error_message="non-object",
            opener=lambda *args, **kwargs: (_ for _ in ()).throw(http_error),
        )

    with pytest.raises(ValueError, match="Mud policy API request failed"):
        mud_api_client.request_json(
            method="GET",
            url="http://mud.local/api/test",
            timeout_seconds=8.0,
            error_prefix="Mud policy API request failed",
            non_object_error_message="non-object",
            opener=lambda *args, **kwargs: (_ for _ in ()).throw(URLError("down")),
        )


def test_request_json_rejects_non_object_response_payloads() -> None:
    """Shared request helper should reject non-dict JSON payload responses."""

    with pytest.raises(ValueError, match="must be object"):
        mud_api_client.request_json(
            method="GET",
            url="http://mud.local/api/test",
            timeout_seconds=8.0,
            error_prefix="Mud policy API request failed",
            non_object_error_message="response must be object",
            opener=lambda request, timeout=8.0: _FakeHttpResponse(b"[]"),
        )


def test_fetch_mud_api_json_appends_session_and_filters_blank_query_params() -> None:
    """Authenticated helper should include session id and omit blank query values."""
    captured: dict[str, object] = {}

    def _fake_urlopen(request, timeout=8.0):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        return _FakeHttpResponse(json.dumps({"items": []}).encode("utf-8"))

    runtime = MudApiRuntimeConfig(base_url="http://mud.local:8000", session_id="s1")
    payload = mud_api_client.fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path="/api/policies",
        query_params={"policy_type": "species_block", "status": "", "namespace": "image.blocks"},
        opener=_fake_urlopen,
    )
    assert payload == {"items": []}
    parsed = urlparse(str(captured["url"]))
    assert parsed.path == "/api/policies"
    assert parse_qs(parsed.query) == {
        "policy_type": ["species_block"],
        "namespace": ["image.blocks"],
        "session_id": ["s1"],
    }


def test_fetch_mud_api_json_overrides_query_session_id_with_runtime_session() -> None:
    """Authenticated helper should force runtime session id over caller query values."""

    captured: dict[str, object] = {}

    def _fake_urlopen(request, timeout=8.0):  # noqa: ANN001
        captured["url"] = request.full_url
        return _FakeHttpResponse(json.dumps({"items": []}).encode("utf-8"))

    runtime = MudApiRuntimeConfig(base_url="http://mud.local:8000", session_id="runtime-session")
    payload = mud_api_client.fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path="/api/policies",
        query_params={"session_id": "caller-session"},
        opener=_fake_urlopen,
    )

    assert payload == {"items": []}
    parsed = urlparse(str(captured["url"]))
    assert parse_qs(parsed.query)["session_id"] == ["runtime-session"]


def test_fetch_mud_api_json_anonymous_serializes_json_payload() -> None:
    """Anonymous helper should serialize request body and decode object response."""
    captured: dict[str, object] = {}

    def _fake_urlopen(request, timeout=8.0):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["content_type"] = request.get_header("Content-type")
        captured["timeout"] = timeout
        captured["body"] = request.data.decode("utf-8") if request.data else ""
        return _FakeHttpResponse(b'{"session_id":"session-1","role":"admin"}')

    payload = mud_api_client.fetch_mud_api_json_anonymous(
        base_url="http://mud.local:8000",
        method="POST",
        path="/login",
        body={"username": "admin", "password": "secret"},
        timeout_seconds=3.5,
        opener=_fake_urlopen,
    )
    assert payload == {"session_id": "session-1", "role": "admin"}
    assert captured == {
        "url": "http://mud.local:8000/login",
        "method": "POST",
        "content_type": "application/json",
        "timeout": 3.5,
        "body": '{"username": "admin", "password": "secret"}',
    }
