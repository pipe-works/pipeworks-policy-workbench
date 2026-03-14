"""Unit tests for source/tree/file web service helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from policy_workbench import web_source_services
from policy_workbench.models import (
    PolicyArtifact,
    PolicyFileRole,
    PolicyTreeSnapshot,
)
from policy_workbench.policy_authoring import PolicySelector


def test_build_tree_payload_filters_supported_files_and_maps_selector() -> None:
    """Tree payload should expose only supported artifacts with selector metadata."""

    snapshot = PolicyTreeSnapshot(
        root=Path("/tmp/policies"),
        directories=[],
        artifacts=[
            PolicyArtifact(
                absolute_path=Path("/tmp/policies/image/prompts/scene_v1.txt"),
                relative_path="image/prompts/scene_v1.txt",
                role=PolicyFileRole.PROMPT_TEXT,
                prompt_text="Describe scene",
            ),
            PolicyArtifact(
                absolute_path=Path("/tmp/policies/notes/readme.md"),
                relative_path="notes/readme.md",
                role=PolicyFileRole.UNKNOWN,
                prompt_text=None,
            ),
        ],
    )

    payload = web_source_services.build_tree_payload(
        Path("/tmp/policies"),
        is_supported_editor_file=lambda rel: rel.endswith(".txt"),
        selector_from_relative_path_fn=lambda rel: (
            PolicySelector(
                policy_type="prompt",
                namespace="image.prompts",
                policy_key="scene",
                variant="v1",
            )
            if rel.endswith("scene_v1.txt")
            else None
        ),
        build_policy_tree_snapshot_fn=lambda _root: snapshot,
    )

    assert payload.source_root == "/tmp/policies"
    assert payload.directories == ["image/prompts", "policies"]
    assert len(payload.artifacts) == 1
    artifact = payload.artifacts[0]
    assert artifact.relative_path == "image/prompts/scene_v1.txt"
    assert artifact.policy_type == "prompt"
    assert artifact.namespace == "image.prompts"
    assert artifact.policy_key == "scene"
    assert artifact.variant == "v1"
    assert artifact.is_authorable is True


def test_read_write_and_resolve_file_under_root(tmp_path: Path) -> None:
    """Read/write helpers should enforce path constraints and support round-trips."""

    source_root = tmp_path / "policies"
    source_root.mkdir(parents=True)

    bytes_written = web_source_services.write_policy_file(
        source_root,
        "image/prompts/scene.txt",
        "canonical",
        validate_supported_editor_path=lambda _rel: None,
        resolve_file_under_root=web_source_services.resolve_file_under_root,
    )
    assert bytes_written == len(b"canonical")

    content = web_source_services.read_policy_file(
        source_root,
        "image/prompts/scene.txt",
        validate_supported_editor_path=lambda _rel: None,
        resolve_file_under_root=web_source_services.resolve_file_under_root,
    )
    assert content == "canonical"

    with pytest.raises(ValueError, match="escapes source root"):
        web_source_services.resolve_file_under_root(source_root, "../outside.txt")

    with pytest.raises(FileNotFoundError, match="Policy file not found"):
        web_source_services.read_policy_file(
            source_root,
            "image/prompts/missing.txt",
            validate_supported_editor_path=lambda _rel: None,
            resolve_file_under_root=web_source_services.resolve_file_under_root,
        )
