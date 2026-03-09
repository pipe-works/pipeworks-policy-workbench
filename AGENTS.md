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

Pipeworks Policy Workbench is a dedicated cross-repository policy operations tool.

The repository is intended to centralize:
- policy file editing workflows
- prompt-bearing policy extraction rules
- schema and semantic validation
- controlled mirroring/sync into downstream repos (for example image generator,
  mud server, and descriptor lab)

## Environment

This repo uses `pyenv`.

- `.python-version` is set to `ppw`
- prefer `pyenv exec ...` for all Python, pip, pytest, ruff, black, and mypy commands

Typical setup:

```bash
pyenv local ppw
pyenv exec pip install -e ".[dev]"
```

## Commands

Run these from the repository root:

```bash
pyenv exec pytest -q
pyenv exec ruff check src tests
pyenv exec black --check src tests
pyenv exec mypy src
pyenv exec pw-policy --help
```

Useful targeted commands:

```bash
pyenv exec pytest tests/unit -q
pyenv exec ruff check src tests --fix
pyenv exec black src tests
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

## Architecture Notes

- The CLI entry point is `pw-policy`.
- Policy parsing and extraction logic should stay deterministic and test-driven.
- Cross-repo path mapping must be explicit, versioned, and reviewable.
- Sync actions should support dry-run mode and machine-readable reports.

## Constraints That Matter

- Treat this repository as the policy workflow source of truth, not downstream app repos.
- Favor additive, auditable sync operations over destructive updates.
- Keep extraction behavior strict and predictable to minimize policy drift.
- Add tests for every rule that transforms policy content.

## Working Style

- Prefer small, targeted changes.
- Add or update tests with behavior changes.
- Keep docs and automation contracts aligned.
- Use `_working/` for handover notes and short-lived planning artifacts.

## Notes For Future Agents

- Keep this file aligned with org-wide foundation docs when those are updated.
- If sync contracts change, update README and any CLI docs in the same PR.
