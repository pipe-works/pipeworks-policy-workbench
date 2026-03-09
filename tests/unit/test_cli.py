"""Unit tests for the policy workbench CLI."""

from __future__ import annotations

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


def test_sync_command_parser_defaults() -> None:
    """Sync command should expose dry-run defaults and option flags."""

    parser = cli._build_parser()
    args = parser.parse_args(["sync"])

    assert args.command == "sync"
    assert args.root is None
    assert args.map is None
    assert args.output_format == "text"
    assert args.apply is False
    assert args.yes is False
    assert args.include_unchanged is False


def test_sync_command_parser_custom_flags() -> None:
    """Sync parser should accept all phase-2 flags."""

    parser = cli._build_parser()
    args = parser.parse_args(
        [
            "sync",
            "--root",
            "/tmp/source",
            "--map",
            "/tmp/map.yaml",
            "--format",
            "json",
            "--apply",
            "--yes",
            "--include-unchanged",
        ]
    )

    assert args.command == "sync"
    assert args.root == "/tmp/source"
    assert args.map == "/tmp/map.yaml"
    assert args.output_format == "json"
    assert args.apply is True
    assert args.yes is True
    assert args.include_unchanged is True


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


def test_main_doctor_delegates_to_command_module(monkeypatch) -> None:
    """Doctor command should return the delegated command exit code."""

    monkeypatch.setattr("policy_workbench.cli.run_doctor", lambda *, root, out, err: 5)
    assert cli.main(["doctor", "--root", "/tmp/policies"]) == 5


def test_main_validate_delegates_to_command_module(monkeypatch) -> None:
    """Validate command should return the delegated command exit code."""

    monkeypatch.setattr("policy_workbench.cli.run_validate", lambda *, root, out, err: 6)
    assert cli.main(["validate", "--root", "/tmp/policies"]) == 6


def test_main_sync_delegates_to_command_module(monkeypatch) -> None:
    """Sync command should return delegated command exit code and parsed args."""

    captured: dict[str, object] = {}

    def fake_run_sync(
        *,
        root: str | None,
        map_path: str | None,
        output_format: str,
        apply: bool,
        yes: bool,
        include_unchanged: bool,
        out,
        err,
    ) -> int:
        captured["root"] = root
        captured["map_path"] = map_path
        captured["output_format"] = output_format
        captured["apply"] = apply
        captured["yes"] = yes
        captured["include_unchanged"] = include_unchanged
        return 7

    monkeypatch.setattr("policy_workbench.cli.run_sync", fake_run_sync)

    exit_code = cli.main(
        [
            "sync",
            "--root",
            "/tmp/source",
            "--map",
            "/tmp/map.yaml",
            "--format",
            "json",
            "--apply",
            "--yes",
            "--include-unchanged",
        ]
    )

    assert exit_code == 7
    assert captured == {
        "root": "/tmp/source",
        "map_path": "/tmp/map.yaml",
        "output_format": "json",
        "apply": True,
        "yes": True,
        "include_unchanged": True,
    }
