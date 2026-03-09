"""Unit tests for the policy workbench CLI."""

from __future__ import annotations

from policy_workbench import cli


def test_doctor_command_parser() -> None:
    parser = cli._build_parser()
    args = parser.parse_args(["doctor"])
    assert args.command == "doctor"


def test_main_help_without_subcommand(capsys, monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["pw-policy"])
    cli.main()
    out = capsys.readouterr().out
    assert "Pipeworks policy workbench" in out
