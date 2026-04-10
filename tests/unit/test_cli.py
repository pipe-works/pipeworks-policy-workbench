"""Unit tests for the policy workbench CLI."""

from __future__ import annotations

import os

from policy_workbench import cli


def test_doctor_command_parser() -> None:
    """Doctor command should parse optional root override."""

    parser = cli._build_parser()
    args = parser.parse_args(["doctor", "--root", "/tmp/policies"])
    assert args.command == "doctor"
    assert args.root == "/tmp/policies"


def test_validate_command_parser() -> None:
    """Validate command should parse optional root override."""

    parser = cli._build_parser()
    args = parser.parse_args(["validate", "--root", "/tmp/policies"])
    assert args.command == "validate"
    assert args.root == "/tmp/policies"


def test_serve_command_parser_defaults() -> None:
    """Serve command should include host and optional port flags."""

    parser = cli._build_parser()
    args = parser.parse_args(["serve"])
    assert args.command == "serve"
    assert args.host == "0.0.0.0"
    assert args.port is None


def test_main_help_without_subcommand(capsys) -> None:
    """Running without a command should print parser help text."""

    exit_code = cli.main([])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Pipeworks policy workbench" in out


def test_main_serve_invokes_server(monkeypatch) -> None:
    """Serve command should delegate to ``run_server`` with parsed args."""

    called: dict[str, object] = {}

    def fake_run_server(host: str, requested_port: int | None) -> None:
        called["host"] = host
        called["requested_port"] = requested_port

    monkeypatch.setattr("policy_workbench.cli.run_server", fake_run_server)

    exit_code = cli.main(["serve", "--host", "127.0.0.1", "--port", "8010"])

    assert exit_code == 0
    assert called == {"host": "127.0.0.1", "requested_port": 8010}


def test_main_serve_loads_dotenv_before_run_server(monkeypatch, tmp_path) -> None:
    """CLI should load local .env before delegating to run_server."""

    (tmp_path / ".env").write_text("PW_POLICY_DEFAULT_PORT=8019\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    captured: dict[str, object] = {}

    def fake_run_server(host: str, requested_port: int | None) -> None:
        captured["host"] = host
        captured["requested_port"] = requested_port
        captured["env_port"] = os.getenv("PW_POLICY_DEFAULT_PORT")

    monkeypatch.setattr("policy_workbench.cli.run_server", fake_run_server)
    monkeypatch.delenv("PW_POLICY_DEFAULT_PORT", raising=False)

    exit_code = cli.main(["serve"])

    assert exit_code == 0
    assert captured == {
        "host": "0.0.0.0",
        "requested_port": None,
        "env_port": "8019",
    }


def test_main_doctor_delegates_to_command_module(monkeypatch) -> None:
    """Doctor command should return the delegated command exit code."""

    monkeypatch.setattr("policy_workbench.cli.run_doctor", lambda *, root, out, err: 5)
    assert cli.main(["doctor", "--root", "/tmp/policies"]) == 5


def test_main_validate_delegates_to_command_module(monkeypatch) -> None:
    """Validate command should return the delegated command exit code."""

    monkeypatch.setattr("policy_workbench.cli.run_validate", lambda *, root, out, err: 6)
    assert cli.main(["validate", "--root", "/tmp/policies"]) == 6
