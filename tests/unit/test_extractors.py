"""Unit tests for YAML prompt-text extraction."""

from __future__ import annotations

from policy_workbench.extractors import extract_yaml_text_field


def test_extract_inline_text_value() -> None:
    """Inline scalar values should be extracted directly."""

    raw_yaml = "name: goblin\ntext: A goblin with practical gear.\n"
    assert extract_yaml_text_field(raw_yaml) == "A goblin with practical gear."


def test_extract_inline_text_value_with_quotes() -> None:
    """Inline quoted scalar values should be unwrapped for prompt usage."""

    raw_yaml = 'text: "A quoted prompt fragment."\n'
    assert extract_yaml_text_field(raw_yaml) == "A quoted prompt fragment."


def test_extract_multiline_block_scalar() -> None:
    """Block scalar content should be preserved with line breaks."""

    raw_yaml = (
        "id: goblin_v1\n"
        "text: |\n"
        "  A goblin of pipe-works canon with upright humanoid posture,\n"
        "  human-like hands and feet, weathered practical features.\n"
    )
    assert extract_yaml_text_field(raw_yaml) == (
        "A goblin of pipe-works canon with upright humanoid posture,\n"
        "human-like hands and feet, weathered practical features."
    )


def test_extract_returns_empty_when_text_field_missing() -> None:
    """Missing text fields should produce a deterministic empty result."""

    raw_yaml = "name: goblin\ndescription: missing text field\n"
    assert extract_yaml_text_field(raw_yaml) == ""
