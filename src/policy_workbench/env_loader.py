"""Minimal dotenv loader for local CLI startup.

This keeps `.env` support lightweight without requiring extra runtime
dependencies. The loader is intentionally conservative:
- missing file is ignored
- malformed lines are ignored
- existing environment variables are preserved by default
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_dotenv_if_present(path: str | Path = ".env", *, override: bool = False) -> None:
    """Load key/value pairs from a dotenv file into ``os.environ``.

    Args:
        path: Dotenv file path relative to current working directory.
        override: Whether file values should overwrite existing process env.
    """

    dotenv_path = Path(path)
    if not dotenv_path.exists() or not dotenv_path.is_file():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        env_key = key.strip()
        if not _ENV_KEY_RE.match(env_key):
            continue

        env_value = _parse_value(value.strip())
        if override or env_key not in os.environ:
            os.environ[env_key] = env_value


def _parse_value(value: str) -> str:
    """Parse a dotenv value token with basic quote/comment handling."""

    if not value:
        return ""

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]

    if " #" in value:
        return value.split(" #", 1)[0].rstrip()

    return value
