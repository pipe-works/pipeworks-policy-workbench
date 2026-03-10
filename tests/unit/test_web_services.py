"""Unit tests for targeted web-service helper edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from policy_workbench import web_services


def test_read_optional_text_returns_none_for_none_and_missing_file(tmp_path: Path) -> None:
    """Optional reads should return ``None`` when no readable text file exists."""

    assert web_services._read_optional_text(None) is None
    assert web_services._read_optional_text(tmp_path / "missing.txt") is None


def test_read_optional_text_wraps_decode_errors_as_value_error(tmp_path: Path) -> None:
    """Unreadable bytes should surface as a stable ``ValueError`` contract."""

    binary_path = tmp_path / "invalid.txt"
    binary_path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(ValueError, match="Unable to read text for diff"):
        web_services._read_optional_text(binary_path)


def test_content_signature_and_canonical_label_cover_special_cases() -> None:
    """Signature/label helpers should handle missing/unreadable files and mud-server roots."""

    assert web_services._content_signature(source_content="ignored", exists=False) == "__missing__"
    assert web_services._content_signature(source_content=None, exists=True) == "__unreadable__"

    expected_hash = web_services.compute_payload_hash({"content": "canonical text"})
    assert web_services._content_signature(source_content="canonical text", exists=True) == str(
        expected_hash
    )

    mud_server_root = Path("/tmp/pipeworks_mud_server/data/worlds/pipeworks_web/policies")
    assert web_services._canonical_source_label(mud_server_root) == "canonical-source: mud-server"
