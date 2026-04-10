"""Unit tests for extracted diagnostics/hash web service helpers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from policy_workbench import web_diagnostics_services


def test_compute_tree_hash_is_order_stable() -> None:
    """Tree hash should be deterministic regardless of input entry order."""

    entries_a = [
        web_diagnostics_services.PolicyHashEntry(
            relative_path="image/prompts/b.txt",
            content_hash="h2",
        ),
        web_diagnostics_services.PolicyHashEntry(
            relative_path="image/prompts/a.txt",
            content_hash="h1",
        ),
    ]
    entries_b = list(reversed(entries_a))

    hash_a = web_diagnostics_services.compute_tree_hash(entries=entries_a, ipc_hashing_module=None)
    hash_b = web_diagnostics_services.compute_tree_hash(entries=entries_b, ipc_hashing_module=None)
    assert hash_a == hash_b

    hash_changed = web_diagnostics_services.compute_tree_hash(
        entries=[
            web_diagnostics_services.PolicyHashEntry(
                relative_path="image/prompts/a.txt",
                content_hash="h1-modified",
            ),
            web_diagnostics_services.PolicyHashEntry(
                relative_path="image/prompts/b.txt",
                content_hash="h2",
            ),
        ],
        ipc_hashing_module=None,
    )
    assert hash_changed != hash_a


def test_collect_local_policy_entries_filters_supported_files(tmp_path: Path) -> None:
    """Entry collector should include only supported editor suffixes in sorted order."""

    root = tmp_path / "policy-root"
    (root / "image" / "prompts").mkdir(parents=True)
    (root / "image" / "prompts" / "scene.txt").write_text("scene", encoding="utf-8")
    (root / "image" / "prompts" / "notes.md").write_text("ignore", encoding="utf-8")
    (root / "image" / "blocks").mkdir(parents=True)
    (root / "image" / "blocks" / "goblin.yaml").write_text("text: goblin", encoding="utf-8")

    entries = web_diagnostics_services.collect_local_policy_entries(root)
    assert [entry.relative_path for entry in entries] == [
        "image/blocks/goblin.yaml",
        "image/prompts/scene.txt",
    ]


def test_compute_missing_content_hash_normalizes_path_and_rejects_traversal() -> None:
    """Missing-entry hash helper should normalize equivalent paths and reject escapes."""

    hash_a = web_diagnostics_services.compute_missing_content_hash("./image/prompts/scene.txt")
    hash_b = web_diagnostics_services.compute_missing_content_hash("image/prompts/scene.txt")
    assert hash_a == hash_b

    with pytest.raises(ValueError, match="must not traverse upwards"):
        web_diagnostics_services.compute_missing_content_hash("../outside.txt")


def test_fetch_canonical_hash_snapshot_success_and_error_paths() -> None:
    """Snapshot fetch helper should validate schema and transport failure branches."""

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    payload = {
        "hash_version": "policy_tree_hash_v1",
        "canonical_root": "/tmp/source",
        "generated_at": "2026-03-10T12:00:00Z",
        "file_count": 1,
        "root_hash": "abc123",
        "directories": [],
    }
    snapshot = web_diagnostics_services.fetch_canonical_hash_snapshot(
        "http://canonical.local/api",
        opener=lambda request, timeout=5.0: _FakeResponse(payload),
    )
    assert snapshot.root_hash == "abc123"

    with pytest.raises(ValueError, match="Unable to fetch canonical hash snapshot"):
        web_diagnostics_services.fetch_canonical_hash_snapshot(
            "http://canonical.local/api",
            opener=lambda request, timeout=5.0: (_ for _ in ()).throw(OSError("down")),
        )


def test_misc_diagnostics_helpers_cover_branches(tmp_path: Path) -> None:
    """Small helper utilities should preserve deterministic branch behavior."""

    assert web_diagnostics_services.is_supported_editor_file("scene.yaml") is True
    assert web_diagnostics_services.is_supported_editor_file("scene.md") is False
    with pytest.raises(ValueError, match="Only .txt, .yaml, .yml, and .json"):
        web_diagnostics_services.validate_supported_editor_path("scene.md")

    invalid_utf8_path = tmp_path / "invalid.txt"
    invalid_utf8_path.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="Unable to read text for diff"):
        web_diagnostics_services.read_optional_text(invalid_utf8_path)
    assert web_diagnostics_services.read_optional_text(tmp_path / "missing.txt") is None

    fake_ipc = SimpleNamespace(
        PolicyHashEntry=lambda *, relative_path, content_hash: SimpleNamespace(
            relative_path=relative_path,
            content_hash=content_hash,
        ),
        compute_policy_file_hash=lambda relative_path, _bytes: f"file::{relative_path}",
        compute_policy_tree_hash=lambda entries: f"tree::{len(entries)}",
    )
    assert (
        web_diagnostics_services.compute_file_hash(
            "image/prompts/scene.txt",
            b"content",
            ipc_hashing_module=fake_ipc,
        )
        == "file::image/prompts/scene.txt"
    )
    assert (
        web_diagnostics_services.compute_tree_hash(
            entries=[
                web_diagnostics_services.PolicyHashEntry(
                    relative_path="image/prompts/scene.txt",
                    content_hash="h1",
                )
            ],
            ipc_hashing_module=fake_ipc,
        )
        == "tree::1"
    )
