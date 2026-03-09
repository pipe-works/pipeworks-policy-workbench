"""Unit tests for policy tree scanning and artifact classification."""

from __future__ import annotations

from pathlib import Path

from policy_workbench.models import PolicyFileRole
from policy_workbench.tree_model import build_policy_tree_snapshot


def _write_text(path: Path, content: str) -> None:
    """Write UTF-8 fixture content, creating parent directories as needed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_snapshot_classifies_supported_artifacts(tmp_path: Path) -> None:
    """Scanner should classify common canonical artifact types deterministically."""

    policies_root = tmp_path / "policies"

    _write_text(
        policies_root / "image" / "blocks" / "species" / "goblin_v1.yaml",
        "text: |\n  Canonical goblin prompt.\n",
    )
    _write_text(
        policies_root / "image" / "prompts" / "portrait.txt",
        "Portrait prompt text.",
    )
    _write_text(
        policies_root / "image" / "registries" / "clothing_registry.yaml",
        "entries: []\n",
    )
    _write_text(policies_root / "axis" / "thresholds.yaml", "thresholds: {}\n")
    _write_text(policies_root / "manifest.image.yaml", "version: 1\n")
    _write_text(
        policies_root / "image" / "tone_profiles" / "neutral.json",
        '{"name": "neutral"}',
    )

    snapshot = build_policy_tree_snapshot(policies_root)

    by_path = {artifact.relative_path: artifact for artifact in snapshot.artifacts}

    assert by_path["image/blocks/species/goblin_v1.yaml"].role == PolicyFileRole.PROMPT_YAML
    assert by_path["image/blocks/species/goblin_v1.yaml"].prompt_text == "Canonical goblin prompt."
    assert by_path["image/prompts/portrait.txt"].role == PolicyFileRole.PROMPT_TEXT
    assert by_path["image/registries/clothing_registry.yaml"].role == PolicyFileRole.REGISTRY_YAML
    assert by_path["axis/thresholds.yaml"].role == PolicyFileRole.AXIS_POLICY_YAML
    assert by_path["manifest.image.yaml"].role == PolicyFileRole.MANIFEST_YAML
    assert by_path["image/tone_profiles/neutral.json"].role == PolicyFileRole.TONE_PROFILE_JSON


def test_build_snapshot_marks_non_utf8_files_unknown(tmp_path: Path) -> None:
    """Non-UTF-8 files should be safely captured as unknown artifacts with notes."""

    policies_root = tmp_path / "policies"
    binary_file = policies_root / "image" / "bad.bin"
    binary_file.parent.mkdir(parents=True, exist_ok=True)
    binary_file.write_bytes(b"\xff\xfe\x00\x00")

    snapshot = build_policy_tree_snapshot(policies_root)

    assert len(snapshot.artifacts) == 1
    artifact = snapshot.artifacts[0]
    assert artifact.role == PolicyFileRole.UNKNOWN
    assert any("UTF-8" in note for note in artifact.notes)
