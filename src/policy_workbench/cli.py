"""CLI entry point for policy workbench operations.

The parser and dispatch layer remains intentionally small. Command behavior is
implemented in dedicated modules to keep responsibilities clear and testable.
"""

from __future__ import annotations

import argparse
import sys

from policy_workbench.commands import run_doctor, run_sync, run_validate
from policy_workbench.server import run_server


def _build_parser() -> argparse.ArgumentParser:
    """Create the top-level argument parser and command tree."""

    parser = argparse.ArgumentParser(prog="pw-policy", description="Pipeworks policy workbench")
    subparsers = parser.add_subparsers(dest="command")

    doctor_parser = subparsers.add_parser("doctor", help="Print repository health summary")
    doctor_parser.add_argument(
        "--root",
        default=None,
        help="Optional canonical policy root directory override",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate policy files")
    validate_parser.add_argument(
        "--root",
        default=None,
        help="Optional canonical policy root directory override",
    )

    sync_parser = subparsers.add_parser("sync", help="Plan/apply policy sync across repos")
    sync_parser.add_argument(
        "--root",
        default=None,
        help="Optional source policy root override (takes precedence over mirror map source)",
    )
    sync_parser.add_argument(
        "--map",
        default=None,
        help="Optional mirror map YAML path override (default: config/mirror_map.yaml)",
    )
    sync_parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    sync_parser.add_argument(
        "--include-unchanged",
        action="store_true",
        help="Include unchanged files in output listings",
    )
    sync_parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply create/update changes instead of dry-run planning",
    )
    sync_parser.add_argument(
        "--yes",
        action="store_true",
        help="Required safety confirmation when using --apply",
    )

    serve_parser = subparsers.add_parser("serve", help="Run local policy workbench web server")
    serve_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host interface to bind (default: 0.0.0.0)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Preferred port in 8000-8099; auto-selects another free port in-range if occupied",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute CLI command handling based on parsed arguments.

    Args:
        argv: Optional argument list for testability. When ``None``, argparse
            reads from ``sys.argv``.
    """

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return run_doctor(root=args.root, out=sys.stdout, err=sys.stderr)

    if args.command == "validate":
        return run_validate(root=args.root, out=sys.stdout, err=sys.stderr)

    if args.command == "sync":
        return run_sync(
            root=args.root,
            map_path=args.map,
            output_format=args.output_format,
            apply=args.apply,
            yes=args.yes,
            include_unchanged=args.include_unchanged,
            out=sys.stdout,
            err=sys.stderr,
        )

    if args.command == "serve":
        run_server(host=args.host, requested_port=args.port)
        return 0

    parser.print_help()
    return 0
