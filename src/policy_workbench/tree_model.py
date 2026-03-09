"""Tree scanning and artifact role classification.

This module turns the canonical policy directory into a deterministic snapshot
that downstream validation/sync logic can consume.
"""

from __future__ import annotations

from pathlib import Path

from .extractors import extract_yaml_text_field
from .models import PolicyArtifact, PolicyFileRole, PolicyTreeSnapshot

_YAML_SUFFIXES = {".yaml", ".yml"}
_AXIS_ROOT_FILES = {"axes.yaml", "resolution.yaml", "thresholds.yaml"}


def build_policy_tree_snapshot(root: Path) -> PolicyTreeSnapshot:
    """Scan ``root`` and return a structured snapshot.

    The scan order is path-sorted to keep output deterministic across platforms,
    which helps with stable tests and predictable dry-run sync reports.
    """

    directories = ["policies"]
    directories.extend(
        directory.relative_to(root).as_posix()
        for directory in sorted(path for path in root.rglob("*") if path.is_dir())
    )

    artifacts: list[PolicyArtifact] = []
    for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
        relative_path = file_path.relative_to(root).as_posix()
        artifacts.append(_build_artifact(file_path, relative_path))

    return PolicyTreeSnapshot(root=root, directories=directories, artifacts=artifacts)


def _build_artifact(file_path: Path, relative_path: str) -> PolicyArtifact:
    """Classify one file and attach extracted prompt text where applicable."""

    suffix = file_path.suffix.lower()
    notes: list[str] = []

    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return PolicyArtifact(
            absolute_path=file_path,
            relative_path=relative_path,
            role=PolicyFileRole.UNKNOWN,
            notes=["file is not UTF-8 decodable"],
        )
    except OSError as exc:
        return PolicyArtifact(
            absolute_path=file_path,
            relative_path=relative_path,
            role=PolicyFileRole.UNKNOWN,
            notes=[f"read failed: {exc}"],
        )

    prompt_text: str | None = None

    if suffix == ".txt":
        role = PolicyFileRole.PROMPT_TEXT
        prompt_text = raw_text.strip()
        if not prompt_text:
            notes.append("prompt text file is empty")

    elif suffix in _YAML_SUFFIXES:
        role = _classify_yaml_artifact(relative_path, raw_text)
        if role == PolicyFileRole.PROMPT_YAML:
            prompt_text = extract_yaml_text_field(raw_text)
            if not prompt_text:
                notes.append("prompt-bearing YAML is missing usable text")

    elif suffix == ".json" and "image/tone_profiles/" in relative_path:
        role = PolicyFileRole.TONE_PROFILE_JSON

    else:
        role = PolicyFileRole.UNKNOWN

    return PolicyArtifact(
        absolute_path=file_path,
        relative_path=relative_path,
        role=role,
        prompt_text=prompt_text,
        notes=notes,
    )


def _classify_yaml_artifact(relative_path: str, raw_text: str) -> PolicyFileRole:
    """Classify YAML policy files using path-first and content-second heuristics."""

    filename = Path(relative_path).name

    # Core axis-policy YAMLs are metadata/config, not prompt fragments.
    if relative_path.startswith("axis/") or filename in _AXIS_ROOT_FILES:
        return PolicyFileRole.AXIS_POLICY_YAML

    if filename.startswith("manifest."):
        return PolicyFileRole.MANIFEST_YAML

    if "/registries/" in relative_path:
        return PolicyFileRole.REGISTRY_YAML

    # Prompt-bearing YAML blocks (for example species blocks) are detected by
    # presence of a usable text field.
    if extract_yaml_text_field(raw_text):
        return PolicyFileRole.PROMPT_YAML

    return PolicyFileRole.UNKNOWN
