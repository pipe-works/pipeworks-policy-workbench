"""Unit tests for source/tree/validation web service helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from policy_workbench import web_source_services
from policy_workbench.models import (
    IssueLevel,
    PolicyArtifact,
    PolicyFileRole,
    PolicyTreeSnapshot,
    ValidationIssue,
    ValidationReport,
)
from policy_workbench.policy_authoring import PolicySelector


def test_resolve_source_root_for_web_prefers_explicit_override() -> None:
    """Explicit source root should short-circuit mirror-map resolution."""

    calls: list[str | None] = []

    def _resolve_policy_root(*, explicit_root: str | None) -> Path:
        calls.append(explicit_root)
        return Path("/resolved/explicit")

    resolved = web_source_services.resolve_source_root_for_web(
        root_override="/custom/root",
        map_path_override="ignored.yaml",
        resolve_policy_root_fn=_resolve_policy_root,
        resolve_mirror_map_path_fn=lambda *, explicit_map_path: (_ for _ in ()).throw(
            AssertionError("mirror-map path resolver should not be called")
        ),
        load_mirror_map_fn=lambda _path: (_ for _ in ()).throw(
            AssertionError("mirror-map loader should not be called")
        ),
    )

    assert resolved == Path("/resolved/explicit")
    assert calls == ["/custom/root"]


def test_resolve_source_root_for_web_uses_mirror_map_source_root() -> None:
    """Mirror-map source root should be used when explicit override is absent."""

    class _MirrorMap:
        def __init__(self, source_root: Path | None) -> None:
            self.source_root = source_root

    resolved = web_source_services.resolve_source_root_for_web(
        root_override=None,
        map_path_override=None,
        resolve_policy_root_fn=lambda *, explicit_root: (_ for _ in ()).throw(
            AssertionError("policy-root resolver should not be called")
        ),
        resolve_mirror_map_path_fn=lambda *, explicit_map_path: Path("/tmp/mirror_map.yaml"),
        load_mirror_map_fn=lambda _path: _MirrorMap(Path("/canonical/from-map")),
    )

    assert resolved == Path("/canonical/from-map")


def test_resolve_source_root_for_web_falls_back_when_map_has_no_source() -> None:
    """Policy-root resolver should be used when map omits source.root."""

    class _MirrorMap:
        source_root = None

    calls: list[str | None] = []

    def _resolve_policy_root(*, explicit_root: str | None) -> Path:
        calls.append(explicit_root)
        return Path("/resolved/fallback")

    resolved = web_source_services.resolve_source_root_for_web(
        root_override=None,
        map_path_override=None,
        resolve_policy_root_fn=_resolve_policy_root,
        resolve_mirror_map_path_fn=lambda *, explicit_map_path: Path("/tmp/mirror_map.yaml"),
        load_mirror_map_fn=lambda _path: _MirrorMap(),
    )

    assert resolved == Path("/resolved/fallback")
    assert calls == [None]


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


def test_build_validation_payload_uses_filtered_snapshot() -> None:
    """Validation payload should count issues from the filtered snapshot report."""

    snapshot = PolicyTreeSnapshot(root=Path("/tmp/policies"), directories=[], artifacts=[])
    report = ValidationReport(
        root=Path("/tmp/policies"),
        issues=[
            ValidationIssue(
                level=IssueLevel.WARNING,
                code="warn_1",
                message="warn",
                relative_path="a.txt",
            ),
            ValidationIssue(
                level=IssueLevel.ERROR,
                code="error_1",
                message="error",
                relative_path="b.txt",
            ),
        ],
    )
    filtered = {"called": False}

    def _filter_snapshot(input_snapshot: PolicyTreeSnapshot) -> PolicyTreeSnapshot:
        filtered["called"] = True
        assert input_snapshot is snapshot
        return input_snapshot

    payload = web_source_services.build_validation_payload(
        Path("/tmp/policies"),
        filter_snapshot_to_supported_files=_filter_snapshot,
        build_policy_tree_snapshot_fn=lambda _source_root: snapshot,
        validate_snapshot_fn=lambda _filtered_snapshot: report,
    )

    assert filtered["called"] is True
    assert payload.source_root == "/tmp/policies"
    assert payload.source_kind == "local_mirror_snapshot"
    assert payload.canonical_authority == "mud_server_policy_api"
    assert "local mirror files only" in payload.detail
    assert payload.counts == {"error": 1, "warning": 1, "info": 0}
    assert [issue.code for issue in payload.issues] == ["warn_1", "error_1"]
