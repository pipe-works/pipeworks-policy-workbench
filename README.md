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
- not a replacement for `pipeworks_mud_server` or its admin/runtime authority
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
- `deploy/`
  - checked-in systemd, nginx, and host-env templates for the Luminal service
    surface

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

- it has a dedicated Luminal venv at
  `/srv/work/pipeworks/venvs/pw-policy-workbench`
- it is now a real browser-facing Luminal service at
  `https://policies.pipeworks.luminal.local/`
- the backend runs through `pipeworks-policy-workbench.service`
  on `127.0.0.1:8040` behind nginx
- local ad hoc `pw-policy serve` still exists, but it is no longer the only
  supported browser entry path on Luminal

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
- the current Luminal service env points `server_dev` at the host-local
  mud-server runtime on `http://127.0.0.1:18000`

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
$VENV/bin/pw-policy serve --host 0.0.0.0 --port 8010
```

Behavior:

- runs the FastAPI workbench through Uvicorn
- binds to `127.0.0.1` by default
- chooses an available port in `8000-8099`
- honors `PW_POLICY_DEFAULT_PORT` as a preferred port when set
- use `--host 0.0.0.0` only for explicit ad hoc LAN/debug exposure

## Luminal Service

The workbench now has a real Luminal browser surface:

- hostname: `https://policies.pipeworks.luminal.local/`
- systemd unit: `pipeworks-policy-workbench.service`
- backend bind: `127.0.0.1:8040`
- nginx front door: `/etc/nginx/sites-available/policies.pipeworks.luminal.local`
- host env file: `/etc/pipeworks/policy-workbench/policy-workbench.env`

Checked-in service templates live in:

- `deploy/systemd/pipeworks-policy-workbench.service`
- `deploy/nginx/policies.pipeworks.luminal.local`
- `deploy/etc/pipeworks/policy-workbench/policy-workbench.env.example`

The current service posture is intentionally narrow:

- nginx and the HTTPS hostname are the canonical browser entrypoint
- the backend stays localhost-bound
- unauthenticated browser access is expected to render the shell but block
  policy inventory and save workflows until a valid mud-server admin or
  superuser session is established

## Safety Boundaries

- Keep runtime-mode selection explicit so users can tell which mud-server
  target is active.
- Preserve clear auth/permission behavior for mud-server API failures.
- Keep the backend localhost-bound in steady state on Luminal.
- Do not blur the workbench surface into the existing mud-server admin surface.
- Do not assume browser reachability changes the upstream authority boundary:
  mud-server still owns canonical runtime policy behavior.

## Current Documentation Position

The repo is now documented around the shared-host Luminal model, the live
`policies.pipeworks.luminal.local` service surface, and the API-first
canonical authoring model.

Related Luminal documentation:

- [PipeWorks on Luminal](/home/aapark/dotfiles/docs/project_maps/pipeworks.md)
- [Luminal PipeWorks Policy Workbench Host Preparation](/home/aapark/dotfiles/docs/moc/luminal_pipeworks_policy_workbench_host_preparation.md)

## License

GPL-3.0-or-later. See `LICENSE`.
