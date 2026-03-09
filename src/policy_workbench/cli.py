"""CLI entry point for policy workbench operations."""

from __future__ import annotations

import argparse


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pw-policy", description="Pipeworks policy workbench")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("doctor", help="Print repository health summary")
    subparsers.add_parser("validate", help="Validate policy files (stub)")
    subparsers.add_parser("sync", help="Sync policy files across repos (stub)")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "doctor":
        print("pw-policy: doctor OK (scaffold)")
        return
    if args.command == "validate":
        print("pw-policy: validate not implemented yet")
        return
    if args.command == "sync":
        print("pw-policy: sync not implemented yet")
        return

    parser.print_help()
