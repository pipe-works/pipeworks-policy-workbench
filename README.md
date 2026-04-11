[![CI](https://github.com/pipe-works/pipeworks-policy-workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/pipe-works/pipeworks-policy-workbench/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pipe-works/pipeworks-policy-workbench/branch/main/graph/badge.svg)](https://codecov.io/gh/pipe-works/pipeworks-policy-workbench)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

# pipeworks-policy-workbench

`pipeworks-policy-workbench` is the operator and developer workbench for
PipeWorks policy objects. It combines a CLI and a FastAPI web application so
policy files and mud-server policy APIs can be inspected, validated, and worked
with without editing downstream artifacts by hand.

## PipeWorks Workspace

These repositories are designed to live inside a shared PipeWorks workspace
rooted at `/srv/work/pipeworks`.

- `repos/` contains source checkouts only.
- `venvs/` contains per-project virtual environments such as `pw-mud-server`.
- `runtime/` contains mutable runtime state such as databases, exports, session
  files, and caches.
- `logs/` contains service-owned log output when a project writes logs outside
  the process manager.
- `config/` contains workspace-level configuration files that should not be
  treated as source.
- `bin/` contains optional workspace helper scripts.
- `home/` is reserved for workspace-local user data when a project needs it.

Across the PipeWorks ecosphere, the rule is simple: keep source in `repos/`,
keep mutable state outside the repo checkout, and use explicit paths between
repos when one project depends on another.

## What This Repo Owns

This repository is the source of truth for:

- the `pw-policy` CLI
- the local FastAPI web application for policy inventory and authoring flows
- mud-server policy API client logic and runtime-mode selection
- local policy-tree inspection and validation helpers

This repository does not own:

- canonical runtime policy activation state
- mud-server itself
- policy artifact exchange storage

## Main Surfaces

### CLI

The `pw-policy` command currently provides:

- `doctor` for repository health and policy-tree diagnostics
- `validate` for deterministic validation output
- `serve` for running the local web app

### Web App

The FastAPI web app exposes browser workflows for:

- policy inventory browsing
- local source inspection
- mud-server-backed policy save/publish/activation flows
- runtime mode switching against explicit mud-server API base URLs

## Repository Layout

- `src/policy_workbench/cli.py` top-level CLI entry point
- `src/policy_workbench/server.py` Uvicorn startup and port selection
- `src/policy_workbench/web_app.py` FastAPI app factory and routes
- `src/policy_workbench/mud_api_client.py` and related runtime modules
- `src/policy_workbench/policy_authoring.py` authoring and validation helpers
- `src/policy_workbench/static/` and `templates/` browser assets
- `tests/unit/` unit coverage across CLI, validation, and web behavior
- `deploy/` example deployment assets

## Quick Start

### Requirements

- Python `>=3.12`
- a PipeWorks workspace rooted at `/srv/work/pipeworks`
- Git access to the private `pipeworks-ipc` dependency referenced by
  `pyproject.toml`
- access to a running `pipeworks_mud_server` instance if you want live API
  workflows rather than local-only validation

### Install

```bash
python3 -m venv /srv/work/pipeworks/venvs/pw-policy-workbench
/srv/work/pipeworks/venvs/pw-policy-workbench/bin/pip install -e ".[dev]"
```

If you want docs tooling too:

```bash
/srv/work/pipeworks/venvs/pw-policy-workbench/bin/pip install -e ".[dev,docs]"
```

### Prepare Runtime Environment

The CLI will load `.env` automatically when present. A typical workspace setup
is:

```bash
cp .example.env .env
```

The shipped example covers:

- `PW_POLICY_DEV_MUD_API_BASE_URL`
- `PW_POLICY_CANONICAL_ROOT`
- `PW_POLICY_DEFAULT_PORT`

By default, the canonical-root example points at:

- `/srv/work/pipeworks/repos/pipeworks_mud_server/data/worlds/pipeworks_web/policies`

Override that when your active policy source differs.

### Run The CLI

```bash
/srv/work/pipeworks/venvs/pw-policy-workbench/bin/pw-policy doctor
/srv/work/pipeworks/venvs/pw-policy-workbench/bin/pw-policy validate
```

Serve the browser app:

```bash
/srv/work/pipeworks/venvs/pw-policy-workbench/bin/pw-policy serve
```

Or choose a specific port in the supported `8000-8099` range:

```bash
/srv/work/pipeworks/venvs/pw-policy-workbench/bin/pw-policy serve --port 8040
```

## Runtime Conventions

`pw-policy serve` binds to `127.0.0.1` by default and auto-selects an available
port in `8000-8099` unless `--port` or `PW_POLICY_DEFAULT_PORT` is supplied.

The workbench can operate in two broad modes:

- local validation against a policy tree on disk
- live mud-server-backed workflows using explicit API base URLs and a valid
  mud-server session

Useful environment variables in the current codebase include:

- `PW_POLICY_CANONICAL_ROOT`
- `PW_POLICY_DEV_MUD_API_BASE_URL`
- `PW_POLICY_PROD_MUD_API_BASE_URL`
- `PW_POLICY_MUD_API_BASE_URL`
- `PW_POLICY_MUD_SESSION_ID`
- `PW_POLICY_DEFAULT_PORT`

## Validation And Development

Run the main checks from the repo root:

```bash
/srv/work/pipeworks/venvs/pw-policy-workbench/bin/pytest -q
/srv/work/pipeworks/venvs/pw-policy-workbench/bin/ruff check src tests
/srv/work/pipeworks/venvs/pw-policy-workbench/bin/black --check .
/srv/work/pipeworks/venvs/pw-policy-workbench/bin/mypy src
/srv/work/pipeworks/venvs/pw-policy-workbench/bin/pw-policy --help
```

## Deployment Assets

This repo ships deployment examples under `deploy/`, including checked-in nginx
and systemd examples. Treat those as templates, not as machine-specific
documentation.

## Documentation

The repo is primarily self-documented through code, tests, and deploy assets.
Deeper operational detail should live in runbooks or service docs rather than
in this public-facing README.

## License

[GPL-3.0-or-later](LICENSE)
