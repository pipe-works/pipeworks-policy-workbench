"""Unit tests for targeted web-service helper edge cases."""

from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

from policy_workbench import web_services


def test_read_optional_text_returns_none_for_none_and_missing_file(tmp_path: Path) -> None:
    """Optional reads should return ``None`` when no readable text file exists."""

    assert web_services._read_optional_text(None) is None
    assert web_services._read_optional_text(tmp_path / "missing.txt") is None


def test_read_optional_text_wraps_decode_errors_as_value_error(tmp_path: Path) -> None:
    """Unreadable bytes should surface as a stable ``ValueError`` contract."""

    binary_path = tmp_path / "invalid.txt"
    binary_path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(ValueError, match="Unable to read text for diff"):
        web_services._read_optional_text(binary_path)


def test_content_signature_and_canonical_label_cover_special_cases() -> None:
    """Signature/label helpers should handle missing/unreadable files and mud-server roots."""

    assert web_services._content_signature(source_content="ignored", exists=False) == "__missing__"
    assert web_services._content_signature(source_content=None, exists=True) == "__unreadable__"

    expected_hash = web_services.compute_payload_hash({"content": "canonical text"})
    assert web_services._content_signature(source_content="canonical text", exists=True) == str(
        expected_hash
    )

    mud_server_root = Path("/tmp/pipeworks_mud_server/data/worlds/pipeworks_web/policies")
    assert web_services._canonical_source_label(mud_server_root) == "canonical-source: mud-server"


def test_resolve_mud_api_runtime_config_uses_env_and_override(monkeypatch) -> None:
    """Mud API runtime config should normalize URL and prefer explicit session override."""

    monkeypatch.setenv("PW_POLICY_MUD_API_BASE_URL", " http://mud.local:8123/ ")
    monkeypatch.setenv("PW_POLICY_MUD_SESSION_ID", "session-from-env")

    runtime = web_services._resolve_mud_api_runtime_config(session_id_override=None)
    assert runtime.base_url == "http://mud.local:8123"
    assert runtime.session_id == "session-from-env"

    override_runtime = web_services._resolve_mud_api_runtime_config(
        session_id_override="session-override"
    )
    assert override_runtime.session_id == "session-override"

    base_override_runtime = web_services._resolve_mud_api_runtime_config(
        session_id_override=None,
        base_url_override=" https://dev.mud.example:9443/ ",
    )
    assert base_override_runtime.base_url == "https://dev.mud.example:9443"
    assert base_override_runtime.session_id == "session-from-env"


def test_resolve_mud_api_runtime_config_rejects_missing_base_url_and_session(monkeypatch) -> None:
    """Runtime config resolver should fail fast when required inputs are missing."""

    monkeypatch.setenv("PW_POLICY_MUD_API_BASE_URL", "   ")
    monkeypatch.setenv("PW_POLICY_MUD_SESSION_ID", "session-from-env")
    with pytest.raises(ValueError, match="base URL must not be empty"):
        web_services._resolve_mud_api_runtime_config(session_id_override=None)

    monkeypatch.setenv("PW_POLICY_MUD_API_BASE_URL", "http://mud.local:8000")
    monkeypatch.delenv("PW_POLICY_MUD_SESSION_ID", raising=False)
    with pytest.raises(ValueError, match="session id is required"):
        web_services._resolve_mud_api_runtime_config(session_id_override=None)


def test_build_runtime_auth_payload_rejects_non_server_source_kind() -> None:
    """Runtime auth payload should fail closed for non-server source kinds."""

    payload = web_services.build_runtime_auth_payload(
        mode_key="server_dev",
        source_kind="unsupported_source",
        active_server_url=None,
        session_id_override=None,
    )

    assert payload.status == "error"
    assert payload.access_granted is False
    assert payload.session_present is False
    assert payload.detail == "Runtime mode must be server_api."


def test_build_runtime_auth_payload_reports_authorized_session(monkeypatch) -> None:
    """Runtime auth probe should mark session authorized on successful capabilities call."""

    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id=session_id_override or "s1",
        ),
    )
    monkeypatch.setattr(
        web_services,
        "_fetch_mud_api_json",
        lambda **_kwargs: {
            "authorized": True,
            "role": "admin",
            "allowed_policy_types": ["species_block"],
            "allowed_statuses": ["draft"],
        },
    )

    payload = web_services.build_runtime_auth_payload(
        mode_key="server_dev",
        source_kind="server_api",
        active_server_url="http://mud.local:8000",
        session_id_override="s1",
    )

    assert payload.status == "authorized"
    assert payload.access_granted is True
    assert payload.session_present is True
    assert payload.active_server_url == "http://mud.local:8000"


def test_build_runtime_auth_payload_reports_missing_session(monkeypatch) -> None:
    """Runtime auth probe should map missing session to stable missing_session state."""

    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: (_ for _ in ()).throw(
            ValueError("Mud API session id is required (PW_POLICY_MUD_SESSION_ID).")
        ),
    )

    payload = web_services.build_runtime_auth_payload(
        mode_key="server_dev",
        source_kind="server_api",
        active_server_url="http://mud.local:8000",
        session_id_override=None,
    )

    assert payload.status == "missing_session"
    assert payload.access_granted is False
    assert payload.session_present is False


def test_build_runtime_auth_payload_reports_forbidden_role(monkeypatch) -> None:
    """Runtime auth probe should classify non-admin sessions as forbidden."""

    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id="s1",
        ),
    )
    monkeypatch.setattr(
        web_services,
        "_fetch_mud_api_json",
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError(
                "Mud API request failed (GET http://mud.local:8000/api/policy-capabilities): "
                "Policy API requires admin or superuser role."
            )
        ),
    )

    payload = web_services.build_runtime_auth_payload(
        mode_key="server_dev",
        source_kind="server_api",
        active_server_url="http://mud.local:8000",
        session_id_override="s1",
    )

    assert payload.status == "forbidden"
    assert payload.access_granted is False
    assert payload.session_present is True
    assert "role is not admin/superuser" in payload.detail


def test_build_runtime_login_payload_success_and_forbidden_role(monkeypatch) -> None:
    """Runtime login helper should return session data and enforce allowed roles."""

    monkeypatch.setattr(
        web_services,
        "_fetch_mud_api_json_anonymous",
        lambda **_kwargs: {
            "session_id": "session-admin-1",
            "role": "admin",
            "success": True,
            "available_worlds": [{"id": "pipeworks_web", "name": "Pipeworks Web"}],
        },
    )
    success_payload = web_services.build_runtime_login_payload(
        mode_key="server_dev",
        source_kind="server_api",
        active_server_url="http://mud.local:8000",
        username="admin-user",
        password="secret",
    )
    assert success_payload.success is True
    assert success_payload.session_id == "session-admin-1"
    assert success_payload.role == "admin"
    assert success_payload.available_worlds == [{"id": "pipeworks_web", "name": "Pipeworks Web"}]

    monkeypatch.setattr(
        web_services,
        "_fetch_mud_api_json_anonymous",
        lambda **_kwargs: {
            "session_id": "session-player-1",
            "role": "player",
            "success": True,
            "available_worlds": [{"id": "mud_alpha", "name": "Mud Alpha"}],
        },
    )
    forbidden_payload = web_services.build_runtime_login_payload(
        mode_key="server_dev",
        source_kind="server_api",
        active_server_url="http://mud.local:8000",
        username="player-user",
        password="secret",
    )
    assert forbidden_payload.success is False
    assert forbidden_payload.session_id == "session-player-1"
    assert forbidden_payload.role == "player"
    assert forbidden_payload.available_worlds == [{"id": "mud_alpha", "name": "Mud Alpha"}]
    assert "not admin/superuser" in forbidden_payload.detail


def test_build_runtime_login_payload_rejects_non_server_and_missing_credentials() -> None:
    """Runtime login helper should reject non-server source kinds and blank credentials."""

    with pytest.raises(ValueError, match="Runtime mode must be server_api"):
        web_services.build_runtime_login_payload(
            mode_key="server_dev",
            source_kind="unsupported_source",
            active_server_url=None,
            username="admin",
            password="secret",
        )

    with pytest.raises(ValueError, match="Username is required"):
        web_services.build_runtime_login_payload(
            mode_key="server_dev",
            source_kind="server_api",
            active_server_url="http://mud.local:8000",
            username=" ",
            password="secret",
        )

    with pytest.raises(ValueError, match="Password is required"):
        web_services.build_runtime_login_payload(
            mode_key="server_dev",
            source_kind="server_api",
            active_server_url="http://mud.local:8000",
            username="admin",
            password=" ",
        )


def test_build_policy_type_options_payload_requires_server_source_kind() -> None:
    """Policy type options should reject non-server runtime source kinds."""

    with pytest.raises(ValueError, match="Runtime mode must be server_api"):
        web_services.build_policy_type_options_payload(
            source_kind="local_disk",
            active_server_url=None,
            session_id_override="session-1",
        )


def test_build_policy_type_options_payload_returns_api_values(monkeypatch) -> None:
    """Policy type options should resolve strictly from mud-server capabilities."""

    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id="session-1",
        ),
    )
    monkeypatch.setattr(
        web_services,
        "_fetch_mud_api_json",
        lambda **_kwargs: {
            "allowed_policy_types": ["prompt", "species_block", "prompt"],
            "allowed_statuses": ["draft", "active"],
        },
    )

    payload = web_services.build_policy_type_options_payload(
        source_kind="server_api",
        active_server_url="http://mud.local:8000",
        session_id_override="session-1",
    )
    assert payload.items == ["prompt", "species_block"]
    assert payload.source == "mud_server_api"
    assert payload.detail == "Policy types resolved from mud-server policy capabilities."


def test_build_policy_type_options_payload_raises_when_api_unavailable(
    monkeypatch,
) -> None:
    """Policy type options should surface API/session discovery errors explicitly."""

    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: (_ for _ in ()).throw(
            ValueError("Mud API session id is required (PW_POLICY_MUD_SESSION_ID).")
        ),
    )

    with pytest.raises(ValueError, match="Mud API session id is required"):
        web_services.build_policy_type_options_payload(
            source_kind="server_api",
            active_server_url="http://mud.local:8000",
            session_id_override=None,
        )


def test_build_policy_namespace_options_payload_returns_api_values(monkeypatch) -> None:
    """Namespace options should resolve strictly from mud-server API inventory."""

    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id="session-1",
        ),
    )
    monkeypatch.setattr(
        web_services,
        "_fetch_mud_api_json",
        lambda **_kwargs: {
            "items": [
                {"namespace": "image.blocks.species"},
                {"namespace": "translation.prompts.ic"},
            ]
        },
    )
    payload = web_services.build_policy_namespace_options_payload(
        source_kind="server_api",
        active_server_url="http://mud.local:8000",
        session_id_override="session-1",
        policy_type=None,
    )
    assert payload.items == ["image.blocks.species", "translation.prompts.ic"]
    assert payload.source == "mud_server_api"


def test_build_policy_namespace_options_payload_passes_policy_type_query_param(monkeypatch) -> None:
    """Namespace discovery should pass selected policy type to mud-server API filter."""

    captured_query_params: dict[str, str] = {}

    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id="session-1",
        ),
    )

    def _fake_fetch(*, runtime, method, path, query_params):  # noqa: ANN001
        captured_query_params.update(query_params)
        return {"items": [{"namespace": "image.blocks.species"}]}

    monkeypatch.setattr(web_services, "_fetch_mud_api_json", _fake_fetch)

    payload = web_services.build_policy_namespace_options_payload(
        source_kind="server_api",
        active_server_url="http://mud.local:8000",
        session_id_override="session-1",
        policy_type="species_block",
    )
    assert payload.items == ["image.blocks.species"]
    assert captured_query_params == {"policy_type": "species_block"}


def test_build_policy_namespace_options_payload_raises_on_api_error(monkeypatch) -> None:
    """Namespace options should surface API/session errors explicitly."""

    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: (_ for _ in ()).throw(
            ValueError("missing session")
        ),
    )

    with pytest.raises(ValueError, match="missing session"):
        web_services.build_policy_namespace_options_payload(
            source_kind="server_api",
            active_server_url="http://mud.local:8000",
            session_id_override=None,
            policy_type="species_block",
        )


def test_build_policy_status_options_payload_returns_api_values(monkeypatch) -> None:
    """Status options should resolve strictly from mud-server capabilities."""

    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id="session-1",
        ),
    )
    monkeypatch.setattr(
        web_services,
        "_fetch_mud_api_json",
        lambda **_kwargs: {
            "allowed_policy_types": ["species_block"],
            "allowed_statuses": ["active", "draft", "active"],
        },
    )
    payload = web_services.build_policy_status_options_payload(
        source_kind="server_api",
        active_server_url="http://mud.local:8000",
        session_id_override="session-1",
    )
    assert payload.items == ["active", "draft"]
    assert payload.source == "mud_server_api"
    assert payload.detail == "Statuses resolved from mud-server policy capabilities."


def test_build_policy_status_options_payload_raises_when_api_unavailable(monkeypatch) -> None:
    """Status options should surface API/session errors explicitly."""

    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: (_ for _ in ()).throw(
            ValueError("missing session")
        ),
    )
    with pytest.raises(ValueError, match="missing session"):
        web_services.build_policy_status_options_payload(
            source_kind="server_api",
            active_server_url="http://mud.local:8000",
            session_id_override=None,
        )


def test_load_local_policy_types_from_disk_parses_mud_service_constant(
    monkeypatch, tmp_path: Path
) -> None:
    """Local canonical loader should parse supported policy types from mud-server source."""

    source_file = tmp_path / "policy_service.py"
    source_file.write_text(
        (
            "_SUPPORTED_POLICY_TYPES = {\n"
            "    'species_block',\n"
            "    'registry',\n"
            "    'prompt',\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PW_POLICY_LOCAL_POLICY_TYPES_FILE", str(source_file))

    items, source, detail = web_services._load_local_policy_types_from_disk()
    assert items == ["species_block", "registry", "prompt"]
    assert source == "local_disk"
    assert "Loaded canonical policy types" in str(detail)


def test_load_local_policy_statuses_from_disk_parses_mud_service_constant(
    monkeypatch, tmp_path: Path
) -> None:
    """Local canonical loader should parse supported policy statuses from mud-server source."""

    source_file = tmp_path / "policy_service.py"
    source_file.write_text(
        (
            "_SUPPORTED_STATUSES = {\n"
            "    'draft',\n"
            "    'candidate',\n"
            "    'active',\n"
            "    'archived',\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PW_POLICY_LOCAL_POLICY_TYPES_FILE", str(source_file))

    items, source, detail = web_services._load_local_policy_statuses_from_disk()
    assert items == ["draft", "candidate", "active", "archived"]
    assert source == "local_disk"
    assert "Loaded canonical policy statuses" in str(detail)


def test_load_local_policy_type_and_status_fallback_branches(monkeypatch, tmp_path: Path) -> None:
    """Local loaders should return stable fallbacks for missing/invalid constant sources."""

    monkeypatch.setattr(web_services, "_resolve_local_policy_types_source_path", lambda: None)
    type_items, type_source, type_detail = web_services._load_local_policy_types_from_disk()
    status_items, status_source, status_detail = (
        web_services._load_local_policy_statuses_from_disk()
    )
    assert type_source == "fallback"
    assert status_source == "fallback"
    assert type_items == list(web_services._FALLBACK_POLICY_TYPES)
    assert status_items == list(web_services._FALLBACK_POLICY_STATUSES)
    assert "not found" in str(type_detail)
    assert "not found" in str(status_detail)

    source_file = tmp_path / "policy_service.py"
    source_file.write_text("_SUPPORTED_POLICY_TYPES = set()\n_SUPPORTED_STATUSES = set()\n")
    monkeypatch.setattr(
        web_services, "_resolve_local_policy_types_source_path", lambda: source_file
    )
    monkeypatch.setattr(web_services, "_load_local_constant_set_values", lambda **_kwargs: None)
    type_items, type_source, _ = web_services._load_local_policy_types_from_disk()
    status_items, status_source, _ = web_services._load_local_policy_statuses_from_disk()
    assert type_items == list(web_services._FALLBACK_POLICY_TYPES)
    assert status_items == list(web_services._FALLBACK_POLICY_STATUSES)
    assert type_source == "fallback"
    assert status_source == "fallback"

    monkeypatch.setattr(web_services, "_load_local_constant_set_values", lambda **_kwargs: [])
    type_items, type_source, _ = web_services._load_local_policy_types_from_disk()
    status_items, status_source, _ = web_services._load_local_policy_statuses_from_disk()
    assert type_items == list(web_services._FALLBACK_POLICY_TYPES)
    assert status_items == list(web_services._FALLBACK_POLICY_STATUSES)
    assert type_source == "fallback"
    assert status_source == "fallback"


def test_resolve_local_policy_types_source_path_supports_override_and_default(monkeypatch) -> None:
    """Local source resolver should honor env override and otherwise return workspace default."""

    override_path = "/tmp/custom_policy_service.py"
    monkeypatch.setenv("PW_POLICY_LOCAL_POLICY_TYPES_FILE", override_path)
    assert web_services._resolve_local_policy_types_source_path() == Path(override_path)

    monkeypatch.delenv("PW_POLICY_LOCAL_POLICY_TYPES_FILE", raising=False)
    default_path = web_services._resolve_local_policy_types_source_path()
    assert default_path is not None
    assert str(default_path).endswith(
        "pipeworks_mud_server/src/mud_server/services/policy_service.py"
    )


def test_build_runtime_login_payload_rejects_empty_base_url_and_invalid_login_payload(
    monkeypatch,
) -> None:
    """Runtime login helper should fail fast for empty URL and malformed login responses."""

    with pytest.raises(ValueError, match="base URL must not be empty"):
        web_services.build_runtime_login_payload(
            mode_key="server_dev",
            source_kind="server_api",
            active_server_url="   ",
            username="admin",
            password="secret",
        )

    monkeypatch.setattr(
        web_services,
        "_fetch_mud_api_json_anonymous",
        lambda **_kwargs: {"role": "admin"},
    )
    with pytest.raises(ValueError, match="did not include session_id"):
        web_services.build_runtime_login_payload(
            mode_key="server_dev",
            source_kind="server_api",
            active_server_url="http://mud.local:8000",
            username="admin",
            password="secret",
        )

    monkeypatch.setattr(
        web_services,
        "_fetch_mud_api_json_anonymous",
        lambda **_kwargs: {"session_id": "session-1"},
    )
    with pytest.raises(ValueError, match="did not include role"):
        web_services.build_runtime_login_payload(
            mode_key="server_dev",
            source_kind="server_api",
            active_server_url="http://mud.local:8000",
            username="admin",
            password="secret",
        )


def test_normalize_base_url_trims_and_handles_blank_values() -> None:
    """Base URL normalizer should trim trailing slash and keep blank values stable."""

    assert (
        web_services._normalize_base_url(" https://dev.example.test/ ")
        == "https://dev.example.test"
    )
    assert web_services._normalize_base_url("  ") == ""
    assert web_services._normalize_base_url(None) == ""


def test_extract_capabilities_string_list_rejects_missing_field() -> None:
    """Capabilities extractor should reject payloads missing required list fields."""

    with pytest.raises(ValueError, match="must include 'allowed_policy_types'"):
        web_services._extract_string_list_from_capabilities_payload(
            payload={"not_items": []},
            field_name="allowed_policy_types",
        )


def test_extract_namespaces_from_inventory_payload_rejects_missing_items() -> None:
    """Namespace extraction should reject inventory payloads without an items list."""

    with pytest.raises(ValueError, match="must include an 'items' list"):
        web_services._extract_namespaces_from_inventory_payload({"not_items": []})


def test_extract_capabilities_string_list_dedupes_and_normalizes() -> None:
    """Capabilities extractor should normalize string lists and preserve first-seen order."""

    types = web_services._extract_string_list_from_capabilities_payload(
        payload={"allowed_policy_types": ["species_block", "", "species_block", "prompt"]},
        field_name="allowed_policy_types",
    )
    namespaces = web_services._extract_namespaces_from_inventory_payload(
        {"items": [{"namespace": "image.blocks.species"}, 7, {"namespace": "image.blocks.species"}]}
    )
    statuses = web_services._extract_string_list_from_capabilities_payload(
        payload={"allowed_statuses": ["draft", "draft", "active", ""]},
        field_name="allowed_statuses",
    )
    assert types == ["species_block", "prompt"]
    assert namespaces == ["image.blocks.species"]
    assert statuses == ["draft", "active"]


def test_fetch_policy_capabilities_payload_uses_canonical_endpoint(monkeypatch) -> None:
    """Capability fetch helper should call mud-server /api/policy-capabilities exactly."""

    captured_path = {"value": None}

    def _fake_fetch(*, runtime, method, path, query_params):  # noqa: ANN001
        captured_path["value"] = (runtime.base_url, method, path, query_params)
        return {
            "authorized": True,
            "role": "admin",
            "allowed_policy_types": ["species_block"],
            "allowed_statuses": ["draft"],
        }

    monkeypatch.setattr(web_services, "_fetch_mud_api_json", _fake_fetch)

    runtime = web_services._MudApiRuntimeConfig(base_url="http://mud.local:8000", session_id="s1")
    payload = web_services._fetch_policy_capabilities_payload(runtime=runtime)

    assert payload["authorized"] is True
    assert captured_path["value"] == (
        "http://mud.local:8000",
        "GET",
        "/api/policy-capabilities",
        {},
    )


def test_load_local_namespaces_from_disk_filters_supported_paths(
    monkeypatch, tmp_path: Path
) -> None:
    """Namespace discovery should include authorable files and respect type filters."""

    source_root = tmp_path / "policies"
    (source_root / "image" / "blocks" / "species").mkdir(parents=True)
    (source_root / "image" / "tone_profiles").mkdir(parents=True)
    (source_root / "image" / "blocks" / "species" / "goblin_v1.yaml").write_text("text: test")
    (source_root / "image" / "tone_profiles" / "ledger_engraving_v1.json").write_text("{}")
    (source_root / "notes.md").write_text("ignore me")

    # Ensure only supported extensions are considered by this helper.
    monkeypatch.setattr(
        web_services,
        "_is_supported_editor_file",
        lambda rel: not rel.endswith(".md"),
    )

    all_namespaces = web_services._load_local_namespaces_from_disk(
        source_root=source_root,
        policy_type=None,
    )
    species_only = web_services._load_local_namespaces_from_disk(
        source_root=source_root,
        policy_type="species_block",
    )
    missing_root = web_services._load_local_namespaces_from_disk(
        source_root=tmp_path / "does-not-exist",
        policy_type=None,
    )

    assert all_namespaces == ["image.blocks.species", "image.tone_profiles"]
    assert species_only == ["image.blocks.species"]
    assert missing_root == []


def test_load_local_constant_set_values_handles_missing_read_error_and_no_match(
    monkeypatch, tmp_path: Path
) -> None:
    """Constant parser should return None for missing files, read errors, and no matches."""

    missing_values = web_services._load_local_constant_set_values(
        source_path=tmp_path / "missing.py",
        constant_name="_SUPPORTED_POLICY_TYPES",
    )
    assert missing_values is None

    source_file = tmp_path / "policy_service.py"
    source_file.write_text("_SOMETHING_ELSE = {'value'}\n")
    no_match = web_services._load_local_constant_set_values(
        source_path=source_file,
        constant_name="_SUPPORTED_POLICY_TYPES",
    )
    assert no_match is None

    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, encoding="utf-8": (_ for _ in ()).throw(OSError("boom")),
    )
    read_error = web_services._load_local_constant_set_values(
        source_path=source_file,
        constant_name="_SUPPORTED_POLICY_TYPES",
    )
    assert read_error is None


def test_load_local_namespaces_from_disk_handles_outside_and_unmapped_paths(
    monkeypatch, tmp_path: Path
) -> None:
    """Namespace discovery should skip paths outside root and unsupported selector mappings."""

    source_root = tmp_path / "policies"
    source_root.mkdir(parents=True)

    original_rglob = Path.rglob

    def _patched_rglob(self: Path, pattern: str):  # noqa: ANN001
        if self == source_root:
            return [Path("/tmp/outside.txt"), source_root / "image" / "unknown.data"]
        return list(original_rglob(self, pattern))

    monkeypatch.setattr(Path, "rglob", _patched_rglob)
    monkeypatch.setattr(web_services, "_is_supported_editor_file", lambda _rel: True)
    monkeypatch.setattr(web_services, "selector_from_relative_path", lambda _rel: None)

    assert (
        web_services._load_local_namespaces_from_disk(source_root=source_root, policy_type=None)
        == []
    )


def test_load_local_namespaces_from_disk_skips_paths_outside_source_root(
    monkeypatch, tmp_path: Path
) -> None:
    """Namespace loader should skip entries that cannot be relativized under source root."""

    source_root = tmp_path / "policies"
    source_root.mkdir(parents=True)

    class _OutsidePath:
        def is_file(self) -> bool:
            return True

        def relative_to(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
            raise ValueError("outside")

    monkeypatch.setattr(Path, "rglob", lambda self, pattern: [_OutsidePath()])
    assert (
        web_services._load_local_namespaces_from_disk(source_root=source_root, policy_type=None)
        == []
    )


def test_load_local_namespaces_from_disk_skips_unmapped_supported_files(
    monkeypatch, tmp_path: Path
) -> None:
    """Namespace loader should skip supported files that have no canonical selector mapping."""

    source_root = tmp_path / "policies"
    source_root.mkdir(parents=True)

    class _MappedPath:
        def is_file(self) -> bool:
            return True

        def relative_to(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
            return Path("image/unknown/entry_v1.yaml")

    monkeypatch.setattr(Path, "rglob", lambda self, pattern: [_MappedPath()])
    monkeypatch.setattr(web_services, "_is_supported_editor_file", lambda _rel: True)
    monkeypatch.setattr(web_services, "selector_from_relative_path", lambda _rel: None)

    assert (
        web_services._load_local_namespaces_from_disk(source_root=source_root, policy_type=None)
        == []
    )


def test_fetch_mud_api_json_builds_url_and_returns_object_payload(monkeypatch) -> None:
    """Transport helper should append session_id and parse object JSON responses."""

    class _FakeHttpResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def __enter__(self) -> _FakeHttpResponse:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    captured: dict[str, str] = {}

    def _fake_urlopen(request, timeout=8.0):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["timeout"] = str(timeout)
        return _FakeHttpResponse({"items": []})

    monkeypatch.setattr(web_services, "urlopen", _fake_urlopen)

    runtime = web_services._MudApiRuntimeConfig(base_url="http://mud.local:8000", session_id="s1")
    payload = web_services._fetch_mud_api_json(
        runtime=runtime,
        method="GET",
        path="/api/policies",
        query_params={"policy_type": "species_block", "status": "draft", "empty": ""},
    )

    assert payload == {"items": []}
    assert captured["method"] == "GET"
    assert captured["timeout"] == "8.0"
    parsed = urlparse(captured["url"])
    assert parsed.path == "/api/policies"
    assert parse_qs(parsed.query) == {
        "policy_type": ["species_block"],
        "status": ["draft"],
        "session_id": ["s1"],
    }


def test_fetch_mud_api_json_maps_http_transport_and_schema_errors(monkeypatch) -> None:
    """Transport helper should raise stable ValueError messages across failure modes."""

    runtime = web_services._MudApiRuntimeConfig(base_url="http://mud.local:8000", session_id="s1")

    http_error = HTTPError(
        url="http://mud.local:8000/api/policies",
        code=403,
        msg="Forbidden",
        hdrs=None,
        fp=io.BytesIO(b'{"code":"forbidden","detail":"denied"}'),
    )
    monkeypatch.setattr(
        web_services, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(http_error)
    )
    with pytest.raises(ValueError, match="forbidden: denied"):
        web_services._fetch_mud_api_json(
            runtime=runtime,
            method="GET",
            path="/api/policies",
            query_params={},
        )

    monkeypatch.setattr(
        web_services,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("connection refused")),
    )
    with pytest.raises(ValueError, match="connection refused"):
        web_services._fetch_mud_api_json(
            runtime=runtime,
            method="GET",
            path="/api/policies",
            query_params={},
        )

    class _ArrayHttpResponse:
        def __enter__(self) -> _ArrayHttpResponse:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return b'["invalid"]'

    monkeypatch.setattr(web_services, "urlopen", lambda *_args, **_kwargs: _ArrayHttpResponse())
    with pytest.raises(ValueError, match="must be a JSON object"):
        web_services._fetch_mud_api_json(
            runtime=runtime,
            method="GET",
            path="/api/policies",
            query_params={},
        )


def test_fetch_mud_api_json_anonymous_covers_success_and_failures(monkeypatch) -> None:
    """Anonymous transport helper should serialize body and normalize failure contracts."""

    class _FakeHttpResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def __enter__(self) -> _FakeHttpResponse:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    captured: dict[str, object] = {}

    def _fake_urlopen(request, timeout=8.0):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        captured["body"] = request.data.decode("utf-8") if request.data else ""
        return _FakeHttpResponse({"session_id": "session-1", "role": "admin"})

    monkeypatch.setattr(web_services, "urlopen", _fake_urlopen)
    payload = web_services._fetch_mud_api_json_anonymous(
        base_url="http://mud.local:8000",
        method="POST",
        path="/login",
        body={"username": "admin", "password": "secret"},
        timeout_seconds=3.5,
    )
    assert payload["session_id"] == "session-1"
    assert captured == {
        "url": "http://mud.local:8000/login",
        "method": "POST",
        "timeout": 3.5,
        "body": '{"username": "admin", "password": "secret"}',
    }

    http_error = HTTPError(
        url="http://mud.local:8000/login",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=io.BytesIO(b'{"detail":"bad credentials"}'),
    )
    monkeypatch.setattr(
        web_services, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(http_error)
    )
    with pytest.raises(ValueError, match="bad credentials"):
        web_services._fetch_mud_api_json_anonymous(
            base_url="http://mud.local:8000",
            method="POST",
            path="/login",
            body={"username": "admin", "password": "secret"},
        )

    monkeypatch.setattr(
        web_services,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("connection refused")),
    )
    with pytest.raises(ValueError, match="connection refused"):
        web_services._fetch_mud_api_json_anonymous(
            base_url="http://mud.local:8000",
            method="POST",
            path="/login",
            body={"username": "admin", "password": "secret"},
        )

    class _ArrayHttpResponse:
        def __enter__(self) -> _ArrayHttpResponse:
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return b'["invalid"]'

    monkeypatch.setattr(web_services, "urlopen", lambda *_args, **_kwargs: _ArrayHttpResponse())
    with pytest.raises(ValueError, match="must be a JSON object"):
        web_services._fetch_mud_api_json_anonymous(
            base_url="http://mud.local:8000",
            method="POST",
            path="/login",
            body={"username": "admin", "password": "secret"},
        )


def test_build_policy_inventory_payload_filters_and_serializes_items(monkeypatch) -> None:
    """Inventory builder should normalize filters and return summary rows."""

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id=(session_id_override or "s1"),
        ),
    )

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

    monkeypatch.setattr(web_services, "_fetch_mud_api_json", _fake_fetch)

    payload = web_services.build_policy_inventory_payload(
        policy_type=" species_block ",
        namespace=" image.blocks.species ",
        status=" draft ",
        session_id_override="session-1",
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


def test_build_inventory_uses_base_url_override_for_runtime_resolution(monkeypatch) -> None:
    """Inventory builder should pass optional API base URL override to runtime resolver."""
    captured: dict[str, object] = {}

    def _fake_runtime(*, session_id_override=None, base_url_override=None):
        captured["session_id_override"] = session_id_override
        captured["base_url_override"] = base_url_override
        return web_services._MudApiRuntimeConfig(
            base_url="https://dev.mud.example:9443",
            session_id="s1",
        )

    monkeypatch.setattr(web_services, "_resolve_mud_api_runtime_config", _fake_runtime)
    monkeypatch.setattr(web_services, "_fetch_mud_api_json", lambda **_kwargs: {"items": []})

    payload = web_services.build_policy_inventory_payload(
        policy_type=None,
        namespace=None,
        status=None,
        session_id_override="session-1",
        base_url_override="https://dev.mud.example:9443",
    )
    assert payload.item_count == 0
    assert captured == {
        "session_id_override": "session-1",
        "base_url_override": "https://dev.mud.example:9443",
    }


def test_build_policy_inventory_payload_rejects_invalid_item_shapes(monkeypatch) -> None:
    """Inventory builder should reject malformed mud-server payload contracts."""

    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id="s1",
        ),
    )

    monkeypatch.setattr(web_services, "_fetch_mud_api_json", lambda **_kwargs: {"items": "bad"})
    with pytest.raises(ValueError, match="must include 'items' list"):
        web_services.build_policy_inventory_payload(
            policy_type=None,
            namespace=None,
            status=None,
            session_id_override=None,
        )

    monkeypatch.setattr(web_services, "_fetch_mud_api_json", lambda **_kwargs: {"items": [1]})
    with pytest.raises(ValueError, match="must be JSON objects"):
        web_services.build_policy_inventory_payload(
            policy_type=None,
            namespace=None,
            status=None,
            session_id_override=None,
        )


def test_build_policy_detail_activation_and_publish_payloads(monkeypatch) -> None:
    """Detail/activation/publish builders should call expected mud API routes."""

    captured_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id=(session_id_override or "s1"),
        ),
    )

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
                        "activated_at": "2026-03-11T21:00:00Z",
                        "activated_by": "tester",
                        "rollback_of_activation_id": None,
                        "audit_event_id": 101,
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

    monkeypatch.setattr(web_services, "_fetch_mud_api_json", _fake_fetch)

    detail_payload = web_services.build_policy_object_detail_payload(
        policy_id="species_block:image.blocks.species:goblin/v1",
        variant=" v1 ",
        session_id_override="session-1",
    )
    assert detail_payload.variant == "v1"

    activation_payload = web_services.build_policy_activation_scope_payload(
        scope="pipeworks_web:mobile",
        effective=False,
        session_id_override="session-1",
    )
    assert activation_payload.world_id == "pipeworks_web"
    assert activation_payload.items[0]["policy_id"] == "species_block:image.blocks.species:goblin"

    publish_payload = web_services.build_policy_publish_run_payload(
        publish_run_id=9,
        session_id_override="session-1",
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


def test_build_policy_activation_set_payload_posts_canonical_activation_body(monkeypatch) -> None:
    """Activation-set builder should post normalized payload to mud-server route."""

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        web_services,
        "_resolve_mud_api_runtime_config",
        lambda session_id_override=None, base_url_override=None: web_services._MudApiRuntimeConfig(
            base_url="http://mud.local:8000",
            session_id=(session_id_override or "s1"),
        ),
    )

    def _fake_fetch(*, runtime, method, path, query_params, json_payload=None):  # noqa: ANN001
        captured["runtime"] = runtime
        captured["method"] = method
        captured["path"] = path
        captured["query_params"] = query_params
        captured["json_payload"] = json_payload
        return {
            "world_id": "pipeworks_web",
            "client_profile": None,
            "policy_id": "descriptor_layer:image.descriptors:id_card",
            "variant": "v1-w-pipeworks-web",
            "activated_at": "2026-03-15T12:00:00Z",
            "activated_by": "tester",
            "rollback_of_activation_id": None,
            "audit_event_id": 301,
        }

    monkeypatch.setattr(web_services, "_fetch_mud_api_json", _fake_fetch)

    payload = web_services.build_policy_activation_set_payload(
        world_id=" pipeworks_web ",
        client_profile="",
        policy_id=" descriptor_layer:image.descriptors:id_card ",
        variant=" v1-w-pipeworks-web ",
        activated_by=" tester ",
        session_id_override="session-1",
    )

    assert payload.world_id == "pipeworks_web"
    assert payload.audit_event_id == 301
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/policy-activations"
    assert captured["query_params"] == {}
    assert captured["json_payload"] == {
        "world_id": "pipeworks_web",
        "client_profile": None,
        "policy_id": "descriptor_layer:image.descriptors:id_card",
        "variant": "v1-w-pipeworks-web",
        "activated_by": "tester",
    }
