"""Unit tests for FastAPI web endpoints in the policy workbench."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from policy_workbench import web_app as web_app_module
from policy_workbench import web_services
from policy_workbench.policy_authoring import PolicySaveResult
from policy_workbench.web_app import create_web_app
from policy_workbench.web_models import HashCanonicalResponse


def _write_text(path: Path, content: str) -> None:
    """Write UTF-8 content to ``path`` and create parents when needed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_mirror_map(path: Path, source_root: Path, target_root: Path) -> None:
    """Create a valid mirror-map config for endpoint integration tests."""

    _write_text(
        path,
        (
            "version: 1\n"
            "source:\n"
            f"  root: {source_root}\n"
            "targets:\n"
            "  - name: mirror-target\n"
            f"    root: {target_root}\n"
        ),
    )


def _build_client(tmp_path: Path) -> tuple[TestClient, Path, Path]:
    """Build a configured ``TestClient`` plus source/target fixture roots."""

    source_root = tmp_path / "source"
    target_root = tmp_path / "target"
    source_root.mkdir(parents=True)
    target_root.mkdir(parents=True)

    _write_text(source_root / "image" / "prompts" / "scene.txt", "new scene prompt")
    _write_text(source_root / "image" / "prompts" / "shared.txt", "same content")
    _write_text(
        source_root / "image" / "blocks" / "species" / "goblin_v1.yaml",
        "text: |\n  A canonical goblin prompt.\n",
    )

    _write_text(target_root / "image" / "prompts" / "scene.txt", "old scene prompt")
    _write_text(target_root / "image" / "prompts" / "shared.txt", "same content")
    _write_text(target_root / "image" / "prompts" / "extra.txt", "target only")

    mirror_map_path = tmp_path / "mirror_map.yaml"
    _write_mirror_map(mirror_map_path, source_root=source_root, target_root=target_root)

    app = create_web_app(
        source_root_override=str(source_root),
        map_path_override=str(mirror_map_path),
    )
    return TestClient(app), source_root, target_root


def test_index_and_health_endpoints_return_expected_payloads(tmp_path: Path) -> None:
    """Root HTML and health endpoints should be available for runtime checks."""

    client, _, _ = _build_client(tmp_path)

    index_response = client.get("/")
    assert index_response.status_code == 200
    assert "Policy Workbench" in index_response.text

    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}


def test_tree_and_file_endpoints_expose_phase2_selector_metadata(tmp_path: Path) -> None:
    """Tree/file APIs should expose selector metadata and keep path safety."""

    client, source_root, _ = _build_client(tmp_path)
    _write_text(source_root / "image" / ".DS_Store", "ignored metadata file")
    _write_text(source_root / "image" / "notes.md", "ignored markdown file")

    tree_response = client.get("/api/tree")
    assert tree_response.status_code == 200
    tree_payload = tree_response.json()
    assert tree_payload["source_root"] == str(source_root)
    assert any(
        item["relative_path"] == "image/prompts/scene.txt" for item in tree_payload["artifacts"]
    )
    species_artifact = next(
        item
        for item in tree_payload["artifacts"]
        if item["relative_path"] == "image/blocks/species/goblin_v1.yaml"
    )
    assert species_artifact["is_authorable"] is True
    assert species_artifact["policy_type"] == "species_block"
    assert species_artifact["namespace"] == "image.blocks.species"
    assert species_artifact["policy_key"] == "goblin"
    assert species_artifact["variant"] == "v1"

    prompt_artifact = next(
        item
        for item in tree_payload["artifacts"]
        if item["relative_path"] == "image/prompts/scene.txt"
    )
    assert prompt_artifact["is_authorable"] is False
    assert prompt_artifact["policy_type"] is None

    assert all(
        Path(item["relative_path"]).suffix.lower() in {".txt", ".yaml", ".yml"}
        for item in tree_payload["artifacts"]
    )
    assert not any(item["relative_path"] == "image/.DS_Store" for item in tree_payload["artifacts"])
    assert not any(item["relative_path"] == "image/notes.md" for item in tree_payload["artifacts"])

    read_response = client.get("/api/file", params={"relative_path": "image/prompts/scene.txt"})
    assert read_response.status_code == 200
    assert read_response.json()["content"] == "new scene prompt"

    write_response = client.put(
        "/api/file",
        json={"relative_path": "image/prompts/scene.txt", "content": "edited prompt text"},
    )
    assert write_response.status_code == 410
    assert "Direct file writes are disabled" in write_response.json()["detail"]

    traversal_response = client.get("/api/file", params={"relative_path": "../escape.txt"})
    assert traversal_response.status_code == 400
    assert "escapes source root" in traversal_response.json()["detail"]

    unsupported_read_response = client.get("/api/file", params={"relative_path": "image/.DS_Store"})
    assert unsupported_read_response.status_code == 400
    assert "Only .txt, .yaml, and .yml" in unsupported_read_response.json()["detail"]

    unsupported_write_response = client.put(
        "/api/file",
        json={"relative_path": "image/notes.md", "content": "should fail"},
    )
    assert unsupported_write_response.status_code == 410
    assert "Direct file writes are disabled" in unsupported_write_response.json()["detail"]


def test_policy_save_endpoint_runs_phase2_api_only_flow(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Policy-save endpoint should call mud-server flow and return normalized payload."""
    client, _, _ = _build_client(tmp_path)

    monkeypatch.setattr(
        web_app_module,
        "resolve_runtime_config",
        lambda session_id_override=None: object(),
    )
    monkeypatch.setattr(
        web_app_module,
        "save_species_block_from_yaml",
        lambda **kwargs: PolicySaveResult(
            policy_id="species_block:image.blocks.species:goblin",
            variant="v1",
            policy_version=3,
            content_hash="hash-123",
            validation_run_id=55,
            activation_audit_event_id=901,
        ),
    )

    response = client.post(
        "/api/policy-save",
        json={
            "policy_type": "species_block",
            "namespace": "image.blocks.species",
            "policy_key": "goblin",
            "variant": "v1",
            "raw_content": "text: |\n  Goblin body text.\n",
            "schema_version": "1.0",
            "status": "candidate",
            "activate": True,
            "world_id": "pipeworks_web",
            "actor": "tester",
            "session_id": "s1",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["policy_id"] == "species_block:image.blocks.species:goblin"
    assert payload["variant"] == "v1"
    assert payload["policy_version"] == 3
    assert payload["validation_run_id"] == 55
    assert payload["activated"] is True
    assert payload["activation_audit_event_id"] == 901


def test_policy_save_endpoint_returns_400_when_runtime_config_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Policy-save endpoint should map runtime/config errors to HTTP 400."""
    client, _, _ = _build_client(tmp_path)
    monkeypatch.setattr(
        web_app_module,
        "resolve_runtime_config",
        lambda session_id_override=None: (_ for _ in ()).throw(ValueError("missing session id")),
    )

    response = client.post(
        "/api/policy-save",
        json={
            "policy_type": "species_block",
            "namespace": "image.blocks.species",
            "policy_key": "goblin",
            "variant": "v1",
            "raw_content": "text: |\n  Goblin body text.\n",
        },
    )
    assert response.status_code == 400
    assert "missing session id" in response.json()["detail"]


def test_validate_endpoint_reports_clean_snapshot(tmp_path: Path) -> None:
    """Validation endpoint should report no issues for clean prompt fixtures."""

    client, source_root, _ = _build_client(tmp_path)
    _write_text(source_root / "image" / ".DS_Store", "ignored metadata file")
    _write_text(source_root / "image" / "notes.md", "ignored markdown file")

    response = client.get("/api/validate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"] == {"error": 0, "warning": 0, "info": 0}
    assert payload["issues"] == []


def test_hash_status_endpoint_returns_drift_counts_for_mismatched_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Hash status endpoint should report canonical drift and per-target counters."""

    client, source_root, _ = _build_client(tmp_path)
    source_entries = web_services._collect_local_policy_entries(source_root)
    canonical_root_hash = web_services._compute_tree_hash(source_entries)
    canonical_snapshot = HashCanonicalResponse(
        hash_version="policy_tree_hash_v1",
        canonical_root=str(source_root),
        generated_at="2026-03-10T12:00:00Z",
        file_count=len(source_entries),
        root_hash=canonical_root_hash,
        directories=[],
    )
    monkeypatch.setattr(
        web_services,
        "_fetch_canonical_hash_snapshot",
        lambda _url: canonical_snapshot,
    )

    response = client.get("/api/hash-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "drift"
    assert payload["canonical"]["root_hash"] == canonical_root_hash
    assert payload["canonical_url"] == "http://127.0.0.1:8000/api/policy/hash-snapshot"
    assert payload["canonical_error"] is None
    assert len(payload["targets"]) == 1
    target = payload["targets"][0]
    assert target["name"] == "mirror-target"
    assert target["file_count"] == 3
    assert target["matches_canonical"] is False
    assert target["missing_count"] == 1
    assert target["different_count"] == 1
    assert target["target_only_count"] == 1


def test_hash_status_endpoint_excludes_target_only_from_match_digest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Target-only files should not force hash mismatch when canonical paths align."""

    client, source_root, target_root = _build_client(tmp_path)
    _write_text(target_root / "image" / "prompts" / "scene.txt", "new scene prompt")
    _write_text(
        target_root / "image" / "blocks" / "species" / "goblin_v1.yaml",
        "text: |\n  A canonical goblin prompt.\n",
    )

    source_entries = web_services._collect_local_policy_entries(source_root)
    canonical_root_hash = web_services._compute_tree_hash(source_entries)
    canonical_snapshot = HashCanonicalResponse(
        hash_version="policy_tree_hash_v1",
        canonical_root=str(source_root),
        generated_at="2026-03-10T12:00:00Z",
        file_count=len(source_entries),
        root_hash=canonical_root_hash,
        directories=[],
    )
    monkeypatch.setattr(
        web_services,
        "_fetch_canonical_hash_snapshot",
        lambda _url: canonical_snapshot,
    )

    response = client.get("/api/hash-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["canonical_url"] == "http://127.0.0.1:8000/api/policy/hash-snapshot"
    assert payload["canonical_error"] is None
    target = payload["targets"][0]
    assert target["file_count"] == 4
    assert target["matches_canonical"] is True
    assert target["missing_count"] == 0
    assert target["different_count"] == 0
    assert target["target_only_count"] == 1


def test_hash_status_endpoint_handles_canonical_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Canonical fetch failure should return canonical_unavailable status, not HTTP failure."""

    client, _, _ = _build_client(tmp_path)
    monkeypatch.setattr(
        web_services,
        "_fetch_canonical_hash_snapshot",
        lambda _url: (_ for _ in ()).throw(ValueError("canonical endpoint unavailable")),
    )

    response = client.get("/api/hash-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "canonical_unavailable"
    assert payload["canonical"] is None
    assert payload["canonical_url"] == "http://127.0.0.1:8000/api/policy/hash-snapshot"
    assert "canonical endpoint unavailable" in payload["canonical_error"]
    assert payload["targets"][0]["file_count"] == 3
    assert payload["targets"][0]["matches_canonical"] is None


def test_hash_status_endpoint_returns_400_when_hash_status_builder_raises(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Hash-status API should convert service-layer errors into HTTP 400."""

    client, _, _ = _build_client(tmp_path)
    monkeypatch.setattr(
        web_app_module,
        "build_hash_status_payload",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("hash status failure")),
    )

    response = client.get("/api/hash-status")

    assert response.status_code == 400
    assert "hash status failure" in response.json()["detail"]


def test_resolve_canonical_hash_snapshot_url_precedence_and_empty_guard(
    monkeypatch,
) -> None:
    """Canonical URL resolver should honor override/env/default precedence."""

    monkeypatch.delenv("PW_POLICY_HASH_SNAPSHOT_URL", raising=False)
    assert web_services._resolve_canonical_hash_snapshot_url("http://override.local/api") == (
        "http://override.local/api"
    )

    monkeypatch.setenv("PW_POLICY_HASH_SNAPSHOT_URL", "http://env.local/api")
    assert web_services._resolve_canonical_hash_snapshot_url(None) == "http://env.local/api"

    monkeypatch.delenv("PW_POLICY_HASH_SNAPSHOT_URL", raising=False)
    assert web_services._resolve_canonical_hash_snapshot_url(None) == (
        "http://127.0.0.1:8000/api/policy/hash-snapshot"
    )

    monkeypatch.setattr(web_services, "_DEFAULT_CANONICAL_HASH_URL", "")
    with pytest.raises(ValueError, match="must not be empty"):
        web_services._resolve_canonical_hash_snapshot_url("   ")


def test_fetch_canonical_hash_snapshot_handles_success_and_error_paths(monkeypatch) -> None:
    """Canonical snapshot fetch helper should validate both payload and transport errors."""

    class _FakeHttpResponse:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._payload

    valid_payload = {
        "hash_version": "policy_tree_hash_v1",
        "canonical_root": "/tmp/source",
        "generated_at": "2026-03-10T12:00:00Z",
        "file_count": 1,
        "root_hash": "abc123",
        "directories": [],
    }
    monkeypatch.setattr(
        web_services,
        "urlopen",
        lambda _request, timeout=5.0: _FakeHttpResponse(json.dumps(valid_payload).encode("utf-8")),
    )
    snapshot = web_services._fetch_canonical_hash_snapshot("http://canonical.local/api")
    assert snapshot.root_hash == "abc123"

    monkeypatch.setattr(
        web_services,
        "urlopen",
        lambda _request, timeout=5.0: (_ for _ in ()).throw(URLError("unreachable")),
    )
    with pytest.raises(ValueError, match="Unable to fetch canonical hash snapshot"):
        web_services._fetch_canonical_hash_snapshot("http://canonical.local/api")

    monkeypatch.setattr(
        web_services,
        "urlopen",
        lambda _request, timeout=5.0: _FakeHttpResponse(json.dumps(valid_payload).encode("utf-8")),
    )
    monkeypatch.setattr(
        web_services.HashCanonicalResponse,
        "model_validate",
        staticmethod(lambda _payload: {}),
    )
    with pytest.raises(ValueError, match="did not match expected schema"):
        web_services._fetch_canonical_hash_snapshot("http://canonical.local/api")


def test_service_hash_helpers_cover_path_guards_and_io_edges(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Service hash helper utilities should enforce path/IO guardrails."""

    assert web_services._normalize_relative_path(r"image\prompts\scene.txt") == (
        "image/prompts/scene.txt"
    )
    with pytest.raises(ValueError, match="must not be empty"):
        web_services._normalize_relative_path("")
    with pytest.raises(ValueError, match="must not traverse upwards"):
        web_services._normalize_relative_path("../scene.txt")

    assert web_services._read_optional_text(None) is None
    assert web_services._read_optional_text(tmp_path / "missing.txt") is None

    directory_path = tmp_path / "directory"
    directory_path.mkdir(parents=True, exist_ok=True)
    assert web_services._read_optional_text(directory_path) is None

    existing_file = tmp_path / "broken.txt"
    existing_file.write_text("content", encoding="utf-8")
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, encoding="utf-8": (_ for _ in ()).throw(OSError("boom")),
    )
    with pytest.raises(ValueError, match="Unable to read text for diff"):
        web_services._read_optional_text(existing_file)


def test_service_hash_helpers_use_ipc_helper_branches(monkeypatch) -> None:
    """Hash helper methods should use IPC implementations when available."""

    class _FakePolicyHashEntry:
        def __init__(self, *, relative_path: str, content_hash: str) -> None:
            self.relative_path = relative_path
            self.content_hash = content_hash

    fake_hashing = SimpleNamespace(
        PolicyHashEntry=_FakePolicyHashEntry,
        compute_policy_file_hash=lambda relative_path, _bytes: f"file::{relative_path}",
        compute_policy_tree_hash=lambda entries: f"tree::{len(entries)}",
    )
    monkeypatch.setattr(web_services, "ipc_hashing", fake_hashing)

    assert web_services._compute_file_hash("image/prompts/scene.txt", b"content") == (
        "file::image/prompts/scene.txt"
    )

    entries = [
        web_services._PolicyHashEntry(relative_path="image/prompts/scene.txt", content_hash="h1"),
        web_services._PolicyHashEntry(relative_path="image/prompts/other.txt", content_hash="h2"),
    ]
    assert web_services._compute_tree_hash(entries) == "tree::2"


def test_sync_plan_and_apply_endpoints_drive_non_destructive_apply(tmp_path: Path) -> None:
    """Sync APIs should classify actions and apply only create/update writes."""

    client, source_root, target_root = _build_client(tmp_path)
    _write_text(source_root / "image" / ".DS_Store", "ignored source metadata file")
    _write_text(source_root / "image" / ".gitkeep", "")
    _write_text(target_root / "image" / ".DS_Store", "ignored target metadata file")
    _write_text(target_root / "image" / "README.md", "ignored markdown file")

    plan_response = client.get("/api/sync-plan", params={"include_unchanged": False})
    assert plan_response.status_code == 200
    plan_payload = plan_response.json()
    assert plan_payload["counts"] == {
        "create": 1,
        "update": 1,
        "unchanged": 1,
        "target_only": 1,
    }
    assert {action["action"] for action in plan_payload["actions"]} == {
        "create",
        "update",
        "target_only",
    }
    assert all(
        Path(action["relative_path"]).suffix.lower() in {".txt", ".yaml", ".yml"}
        for action in plan_payload["actions"]
    )

    compare_response = client.get(
        "/api/sync-compare",
        params={
            "relative_path": "image/prompts/scene.txt",
            "focus_target": "mirror-target",
        },
    )
    assert compare_response.status_code == 200
    compare_payload = compare_response.json()
    assert compare_payload["relative_path"] == "image/prompts/scene.txt"
    assert compare_payload["focus_target"] == "mirror-target"
    assert compare_payload["unique_variant_count"] >= 2

    variants = compare_payload["variants"]
    assert len(variants) == 2
    source_variant = variants[0]
    target_variant = variants[1]
    assert source_variant["kind"] == "source"
    assert source_variant["matches_source"] is True
    assert target_variant["target"] == "mirror-target"
    assert target_variant["action"] == "update"
    assert target_variant["matches_source"] is False
    assert source_variant["content"] == "new scene prompt"
    assert target_variant["content"] == "old scene prompt"

    denied_response = client.post("/api/sync-apply", json={"confirm": False})
    assert denied_response.status_code == 400
    assert denied_response.json()["detail"] == "Sync apply requires confirm=true"

    apply_response = client.post("/api/sync-apply", json={"confirm": True})
    assert apply_response.status_code == 200
    assert apply_response.json() == {"created": 1, "updated": 1, "skipped": 2}

    assert (target_root / "image" / "prompts" / "scene.txt").read_text(encoding="utf-8") == (
        "new scene prompt"
    )
    assert (target_root / "image" / "blocks" / "species" / "goblin_v1.yaml").read_text(
        encoding="utf-8"
    ) == "text: |\n  A canonical goblin prompt.\n"
    assert (target_root / "image" / "prompts" / "extra.txt").read_text(encoding="utf-8") == (
        "target only"
    )


def test_sync_compare_endpoint_rejects_unsupported_file_extensions(tmp_path: Path) -> None:
    """Sync compare should return HTTP 400 when the path is not .txt/.yaml/.yml."""

    client, _, _ = _build_client(tmp_path)

    response = client.get("/api/sync-compare", params={"relative_path": "image/notes.md"})

    assert response.status_code == 400
    assert "Only .txt, .yaml, and .yml" in response.json()["detail"]
