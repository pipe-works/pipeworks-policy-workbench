# pipeworks-policy-workbench

Policy authoring and validation workbench for mud-server canonical policy APIs.

## Purpose

`pipeworks-policy-workbench` is a focused operator and developer tool for
working with canonical policy objects without editing downstream artifacts by
hand.

The repository currently provides two main surfaces:

- `pw-policy`, a CLI for diagnostics, validation, and local serving
- a FastAPI web application for interactive policy workflows backed by
  mud-server APIs

The workbench is designed to reduce policy-editing mistakes by keeping
mud-server policy objects and policy API contracts at the center of the
workflow.

## What The Repo Does

Current codebase responsibilities:

- present policy inventory and policy-object detail views through the web app
- authenticate to mud-server policy APIs for admin/superuser workflows
- validate and save policy variants through mud-server-backed flows
- inspect local canonical policy trees for structural/semantic issues

What this repo is not:

- not the canonical runtime authority for policy activation state
- not automatically a Luminal hosted service just because it includes
  `pw-policy serve`
- not a generic policy warehouse detached from mud-server runtime contracts

## Codebase Shape

Primary package layout under `src/policy_workbench/`:

- `cli.py`
  - CLI entry point for `doctor`, `validate`, and `serve`
- `server.py`
  - Uvicorn startup, serve-port selection, and fallback ASGI app behavior
- `web_app.py`
  - FastAPI app factory, HTML routes, API routes, and browser session handling
- `runtime_mode.py`
  - active mud-server mode selection and URL override handling
- `mud_api_client.py` and `mud_api_runtime.py`
  - mud-server authentication and policy API interactions
- `policy_authoring.py`
  - validation/save helpers for policy object workflows
- `tree_model.py`, `validators.py`, `extractors.py`, `models.py`
  - local policy-tree scanning and validation support
Supporting layout:

- `tests/unit/`
  - unit coverage across CLI, runtime mode, validation, packaging, and
    web/service behavior
- `src/policy_workbench/templates/` and `src/policy_workbench/static/`
  - browser UI assets

## Environment Model

This repo now treats the Luminal host layout as the primary execution model.

It is documented as part of the shared PipeWorks workspace rooted at:

- `/srv/work/pipeworks`

Relevant host paths are:

- repos: `/srv/work/pipeworks/repos`
- venvs: `/srv/work/pipeworks/venvs`
- this repo: `/srv/work/pipeworks/repos/pipeworks-policy-workbench`
- dedicated venv: `/srv/work/pipeworks/venvs/pw-policy-workbench`

Current Luminal posture:

- it is a host-preparation/admin-tool surface, not yet a live hosted service
- it is now validated against a dedicated Luminal venv
- any future promotion into a hostname/nginx/systemd-managed surface should be
  treated as a separate explicit topology decision

Typical setup on Luminal:

```bash
VENV=/srv/work/pipeworks/venvs/pw-policy-workbench

$VENV/bin/pip install -e ".[dev,docs]"
cp .example.env .env
```

Run common validation commands with:

```bash
VENV=/srv/work/pipeworks/venvs/pw-policy-workbench

$VENV/bin/pytest -q
$VENV/bin/ruff check src tests
$VENV/bin/black --check .
$VENV/bin/mypy src
$VENV/bin/pw-policy --help
```

## Runtime Configuration

The CLI loads `.env` automatically when present. Existing exported environment
variables still take precedence over `.env` values.

The example environment file currently exposes:

- `PW_POLICY_DEV_MUD_API_BASE_URL`
  - default mud-server URL for the `server_dev` runtime mode
- `PW_POLICY_DEFAULT_PORT`
  - preferred local serve port in `8000-8099`
- `PW_POLICY_CANONICAL_ROOT`
  - optional canonical policy root override used by CLI validation flows

`PW_POLICY_PROD_MUD_API_BASE_URL` remains available in code, but the example
environment file does not currently set it because the production target is in
transition and should be configured deliberately rather than copied from stale
defaults.

Runtime mode behavior today:

- supported modes are `server_dev` and `server_prod`
- both modes target explicit HTTP(S) mud-server API base URLs
- browser runtime session state is preserved with a hardened cookie plus
  server-side in-memory session binding
- policy API workflows require valid mud-server authentication and appropriate
  admin or superuser role access

## Canonical Policy Root Resolution

CLI commands that scan local policy content resolve the canonical policy root in
this order:

1. `--root`
2. `PW_POLICY_CANONICAL_ROOT`
3. workspace-local defaults

Current default candidate order in code:

1. canonical Luminal workspace path:
   `/srv/work/pipeworks/repos/pipeworks_mud_server/data/worlds/pipeworks_web/policies`
2. sibling repo path:
   `/.../pipeworks_mud_server/data/worlds/pipeworks_web/policies`
3. in-repo fallback path:
   `/.../pipeworks-policy-workbench/data/worlds/pipeworks_web/policies`

On Luminal, that means commands such as `doctor` and `validate` should usually
be run with an explicit root or an exported `PW_POLICY_CANONICAL_ROOT` until
the host-local canonical policy layout is documented more fully.

## Commands

Run these from the repository root with the Luminal venv.

General checks:

```bash
VENV=/srv/work/pipeworks/venvs/pw-policy-workbench

$VENV/bin/pytest -q
$VENV/bin/ruff check src tests
$VENV/bin/black --check .
$VENV/bin/mypy src
```

CLI help:

```bash
VENV=/srv/work/pipeworks/venvs/pw-policy-workbench

$VENV/bin/pw-policy --help
```

Doctor:

```bash
VENV=/srv/work/pipeworks/venvs/pw-policy-workbench

$VENV/bin/pw-policy doctor
$VENV/bin/pw-policy doctor --root /path/to/policies
```

Behavior:

- scans the resolved canonical policy root
- prints compact directory/artifact counts
- reports validation summary counts
- exits non-zero on validation or path-resolution failure

Validate:

```bash
VENV=/srv/work/pipeworks/venvs/pw-policy-workbench

$VENV/bin/pw-policy validate
$VENV/bin/pw-policy validate --root /path/to/policies
```

Behavior:

- emits deterministic line-oriented issue output
- ends with stable summary counts
- is suitable for both human review and automation

Serve:

```bash
VENV=/srv/work/pipeworks/venvs/pw-policy-workbench

$VENV/bin/pw-policy serve
$VENV/bin/pw-policy serve --host 127.0.0.1 --port 8010
```

Behavior:

- runs the FastAPI workbench through Uvicorn
- binds to `0.0.0.0` by default
- chooses an available port in `8000-8099`
- honors `PW_POLICY_DEFAULT_PORT` as a preferred port when set

## Safety Boundaries

- Keep runtime-mode selection explicit so users can tell which mud-server
  target is active.
- Preserve clear auth/permission behavior for mud-server API failures.
- Do not assume local serve behavior implies a host-managed service boundary.

## Current Documentation Position

The repo is now documented around the shared-host Luminal model, with the
legacy mirror/sync workflow removed in favor of the API-first canonical
authoring model.

Related Luminal documentation:

- [PipeWorks on Luminal](/home/aapark/dotfiles/docs/project_maps/pipeworks.md)
- [Luminal PipeWorks Policy Workbench Host Preparation](/home/aapark/dotfiles/docs/moc/luminal_pipeworks_policy_workbench_host_preparation.md)

## License

GPL-3.0-or-later. See `LICENSE`.
