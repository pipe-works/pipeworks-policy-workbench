# AGENTS.md

## Foundation Must-Dos (Org-Wide)

Read and apply these before repo-specific instructions:

- Local workspace path: `../.github/.github/docs/AGENT_FOUNDATION.md`
- Local workspace path: `../.github/.github/docs/TEST_TAGGING_AND_GITHUB_CHECKLIST.md`
- Canonical URL: `https://github.com/pipe-works/.github/blob/main/.github/docs/AGENT_FOUNDATION.md`
- Canonical URL: `https://github.com/pipe-works/.github/blob/main/.github/docs/TEST_TAGGING_AND_GITHUB_CHECKLIST.md`

Mandatory requirements:

1. Run the GitHub preflight checklist before any `gh` interaction, CI edits, or
   test-tag changes.
2. Preserve required checks (`All Checks Passed`, `Secret Scan (Gitleaks)`).
3. Do not weaken test-tag semantics to reduce runtime.
4. Keep CI optimization changes evidence-based (run IDs, timings, check states).

## Project Summary

Pipeworks Policy Workbench is a local authoring and operations surface for
canonical policy work against mud-server APIs.

The repository currently contains two tightly related surfaces:

- a CLI exposed as `pw-policy`
- a FastAPI web application used for interactive policy authoring and runtime
  session management

The current codebase is not a generic policy warehouse and not a long-running
host topology definition by itself. Its concrete responsibilities are:

- present policy inventory and object-detail workflows through a web UI
- authenticate to mud-server policy APIs and keep browser runtime sessions
- validate and save policy variants through mud-server-backed flows
- inspect local policy trees for health and validation issues

## Codebase Shape

Primary package layout under `src/policy_workbench/`:

- `cli.py`
  - top-level argument parsing for `doctor`, `validate`, and `serve`
- `server.py`
  - Uvicorn startup, port selection, and fallback ASGI app behavior
- `web_app.py`
  - FastAPI app factory, HTML routes, API routes, and browser session cookie
    handling
- `runtime_mode.py`
  - active mud-server mode selection and URL override handling
- `policy_authoring.py`
  - save/validate authoring helpers and runtime config resolution
- `mud_api_client.py` and `mud_api_runtime.py`
  - mud-server authentication and policy API interactions
- `web_*services.py` and `web_models.py`
  - web-route payload shaping and response models
- `tree_model.py`, `validators.py`, `extractors.py`, `models.py`
  - local policy tree scanning and validation support
- `pathing.py`
  - canonical root/path resolution logic
- `env_loader.py`
  - lightweight `.env` loading without extra dependency requirements

Supporting repo layout:

- `tests/unit/`
  - unit coverage across CLI, runtime mode, web services, validation, and
    packaging behavior
- `src/policy_workbench/templates/` and `src/policy_workbench/static/`
  - UI template and browser assets

## Environment

This repo now uses the Luminal host layout as its primary execution model.

- workspace root: `/srv/work/pipeworks`
- repo path: `/srv/work/pipeworks/repos/pipeworks-policy-workbench`
- dedicated venv: `/srv/work/pipeworks/venvs/pw-policy-workbench`
- `.example.env` documents local runtime defaults for mud-server URLs and
  preferred serve port
- `.env` is loaded automatically on CLI startup when present

Typical setup:

```bash
VENV=/srv/work/pipeworks/venvs/pw-policy-workbench

$VENV/bin/pip install -e ".[dev,docs]"
cp .example.env .env
```

## Commands

Run these from the repository root:

```bash
VENV=/srv/work/pipeworks/venvs/pw-policy-workbench

$VENV/bin/pytest -q
$VENV/bin/ruff check src tests
$VENV/bin/black --check .
$VENV/bin/mypy src
$VENV/bin/pw-policy --help
```

Important operational commands:

```bash
VENV=/srv/work/pipeworks/venvs/pw-policy-workbench

$VENV/bin/pw-policy doctor
$VENV/bin/pw-policy validate
$VENV/bin/pw-policy serve
```

Current command behavior that matters:

- `doctor`
  - scans the resolved policy root and prints compact health counts
- `validate`
  - emits deterministic line-oriented issue output and summary counts
- `serve`
  - runs the FastAPI workbench through Uvicorn
  - binds to `0.0.0.0` by default
  - chooses an available port in `8000-8099`
  - respects `PW_POLICY_DEFAULT_PORT` as a preferred port when set

## Runtime Model

The current interactive runtime model is mud-server API first.

- supported runtime modes are `server_dev` and `server_prod`
- both modes resolve to explicit HTTP(S) mud-server base URLs
- runtime URL defaults come from environment variables, then in-memory
  overrides set through the application
- the web app stores browser session bindings server-side and issues a hardened
  cookie to preserve that runtime session across refreshes
- route behavior should keep auth and permission failures clearly separated
  (`401` vs `403`) because the UI depends on those coarse categories

## Working Rules

- Keep the CLI thin. Put behavior in dedicated modules rather than growing
  `cli.py`.
- Preserve deterministic output for validation reporting. Downstream automation
  and tests depend on stable ordering and wording.
- Keep runtime mode semantics explicit. Do not add hidden fallback behavior that
  obscures which mud-server target is active.
- Prefer conservative environment handling. Existing exported environment
  variables should continue to win over `.env` file values unless there is a
  strong reason to change that contract.
- Keep browser session and cookie behavior aligned with the current security
  posture in `web_app.py`.

## Testing Expectations

- Add or update tests for every behavior change.
- When changing CLI behavior, update or extend the command/unit coverage first.
- When changing API/web route behavior, update the relevant `web_*` tests.
- When changing pathing behavior, add focused deterministic tests that cover
  both happy path and failure boundaries.
- When changing runtime-mode or auth behavior, verify status-code expectations
  remain stable.

Useful targeted commands:

```bash
VENV=/srv/work/pipeworks/venvs/pw-policy-workbench

$VENV/bin/pytest tests/unit/test_cli.py -q
$VENV/bin/pytest tests/unit/test_runtime_mode.py -q
$VENV/bin/pytest tests/unit/test_web_api.py -q
```

## GitHub and Commit Rules

This repo uses conventional commits and release-please compatible metadata.

- Use `feat:` for user-facing capabilities.
- Use `fix:` for defect corrections.
- Use `docs:` for documentation-only changes.
- Use `test:` for test-only changes.
- Use `ci:` for CI/workflow changes.
- Avoid untagged commit or PR titles.

Before PR creation or merge:

1. Confirm branch, target repo, and PR base branch.
2. Run or reference relevant local validation commands.
3. Ensure required checks remain intact (`All Checks Passed`, `Secret Scan (Gitleaks)`).
4. Include evidence for CI behavior changes (run IDs, timing deltas, check states).

## Notes For Future Agents

- Keep this file aligned with the actual repo, not with older adjacent
  repositories or aspirational architecture.
- If the Luminal host model changes, update README, AGENTS, and host-facing docs in the
  same change rather than leaving environment guidance split across locations.
- If `serve` becomes a deliberately hosted service later, document that as an
  explicit topology decision instead of letting the default local-dev behavior
  imply production posture.
