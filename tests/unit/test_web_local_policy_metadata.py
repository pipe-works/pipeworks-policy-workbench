"""Unit tests for extracted local policy metadata helpers."""

from __future__ import annotations

from pathlib import Path

from policy_workbench import web_local_policy_metadata


def test_resolve_local_policy_types_source_path_supports_override(monkeypatch) -> None:
    """Source-path resolver should honor explicit env override values."""
    override_path = "/tmp/custom_policy_service.py"
    monkeypatch.setenv("PW_POLICY_LOCAL_POLICY_TYPES_FILE", override_path)
    assert web_local_policy_metadata.resolve_local_policy_types_source_path(
        local_policy_types_file_env="PW_POLICY_LOCAL_POLICY_TYPES_FILE",
    ) == Path(override_path)


def test_load_local_constant_set_values_handles_missing_and_parses_set(
    tmp_path: Path,
) -> None:
    """Constant parser should return None for missing files and parse set values."""
    assert (
        web_local_policy_metadata.load_local_constant_set_values(
            source_path=tmp_path / "missing.py",
            constant_name="_SUPPORTED_POLICY_TYPES",
        )
        is None
    )

    source_file = tmp_path / "policy_service.py"
    source_file.write_text("_SUPPORTED_POLICY_TYPES = {'species_block', 'prompt'}\n")
    assert web_local_policy_metadata.load_local_constant_set_values(
        source_path=source_file,
        constant_name="_SUPPORTED_POLICY_TYPES",
    ) == ["species_block", "prompt"]


def test_load_local_policy_type_and_status_metadata_branches() -> None:
    """Local metadata loaders should support fallback and loaded branches."""
    type_items, type_source, type_detail = (
        web_local_policy_metadata.load_local_policy_types_from_disk(
            fallback_policy_types=("species_block", "prompt"),
            resolve_source_path=lambda: None,
            load_constant_set_values=lambda *, source_path, constant_name: None,
            dedupe_preserve_order=lambda values: values,
        )
    )
    assert type_items == ["species_block", "prompt"]
    assert type_source == "fallback"
    assert "not found" in str(type_detail)

    status_items, status_source, _ = web_local_policy_metadata.load_local_policy_statuses_from_disk(
        fallback_policy_statuses=("draft", "active"),
        resolve_source_path=lambda: Path("/tmp/policy_service.py"),
        load_constant_set_values=lambda *, source_path, constant_name: [
            "draft",
            "active",
        ],
        dedupe_preserve_order=lambda values: values,
    )
    assert status_items == ["draft", "active"]
    assert status_source == "local_disk"


def test_load_local_namespaces_from_disk_filters_policy_type(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Namespace loader should include only supported/mapped entries."""
    source_root = tmp_path / "policies"
    (source_root / "image" / "blocks" / "species").mkdir(parents=True)
    (source_root / "image" / "blocks" / "species" / "goblin_v1.yaml").write_text("text: hi")
    (source_root / "notes.md").write_text("ignore")

    class _Selector:
        def __init__(self, policy_type: str, namespace: str) -> None:
            self.policy_type = policy_type
            self.namespace = namespace

    def _selector(relative_path: str):  # noqa: ANN001
        if relative_path.endswith(".yaml"):
            return _Selector("species_block", "image.blocks.species")
        return None

    namespaces = web_local_policy_metadata.load_local_namespaces_from_disk(
        source_root=source_root,
        policy_type="species_block",
        is_supported_editor_file=lambda relative_path: not relative_path.endswith(".md"),
        selector_from_relative_path=_selector,
        dedupe_preserve_order=lambda values: list(dict.fromkeys(values)),
    )
    assert namespaces == ["image.blocks.species"]
