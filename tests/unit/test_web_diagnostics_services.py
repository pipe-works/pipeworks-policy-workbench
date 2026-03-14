"""Unit tests for extracted diagnostics/hash web service helpers."""

from __future__ import annotations

from pathlib import Path

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
