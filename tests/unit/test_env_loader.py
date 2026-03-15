"""Unit tests for dotenv startup loader behavior."""

from __future__ import annotations

import os
from pathlib import Path

from policy_workbench.env_loader import load_dotenv_if_present


def test_load_dotenv_if_present_sets_values_without_overriding_existing(tmp_path: Path) -> None:
    """Loader should populate missing env vars and preserve existing ones."""

    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            [
                "PW_POLICY_DEV_MUD_API_BASE_URL=http://dev.example.test",
                "PW_POLICY_PROD_MUD_API_BASE_URL=https://prod.example.test",
                "PW_POLICY_DEFAULT_PORT=8018",
            ]
        ),
        encoding="utf-8",
    )

    os.environ["PW_POLICY_DEV_MUD_API_BASE_URL"] = "http://already.set"
    os.environ.pop("PW_POLICY_PROD_MUD_API_BASE_URL", None)
    os.environ.pop("PW_POLICY_DEFAULT_PORT", None)

    try:
        load_dotenv_if_present(dotenv_path)
        assert os.environ["PW_POLICY_DEV_MUD_API_BASE_URL"] == "http://already.set"
        assert os.environ["PW_POLICY_PROD_MUD_API_BASE_URL"] == "https://prod.example.test"
        assert os.environ["PW_POLICY_DEFAULT_PORT"] == "8018"
    finally:
        os.environ.pop("PW_POLICY_DEV_MUD_API_BASE_URL", None)
        os.environ.pop("PW_POLICY_PROD_MUD_API_BASE_URL", None)
        os.environ.pop("PW_POLICY_DEFAULT_PORT", None)


def test_load_dotenv_if_present_ignores_missing_file(tmp_path: Path) -> None:
    """Missing dotenv file should not raise and should not mutate env."""

    missing_path = tmp_path / ".env"
    os.environ.pop("PW_POLICY_DEFAULT_PORT", None)
    load_dotenv_if_present(missing_path)
    assert "PW_POLICY_DEFAULT_PORT" not in os.environ
