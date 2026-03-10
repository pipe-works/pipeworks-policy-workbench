"""Unit tests for FastAPI web endpoints in the policy workbench."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from policy_workbench.web_app import create_web_app


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


def test_tree_and_file_endpoints_support_editing_flow(tmp_path: Path) -> None:
    """Tree and file APIs should support read/write loop with path safety."""

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
    assert write_response.status_code == 200
    assert write_response.json()["bytes_written"] == len(b"edited prompt text")

    reread_response = client.get("/api/file", params={"relative_path": "image/prompts/scene.txt"})
    assert reread_response.status_code == 200
    assert reread_response.json()["content"] == "edited prompt text"

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
    assert unsupported_write_response.status_code == 400
    assert "Only .txt, .yaml, and .yml" in unsupported_write_response.json()["detail"]


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
