# Sync Contract v1

## Canonical Contract

1. `mud_server` policy tree is the sole canonical truth.
2. Policy Workbench is the canonical authoring/promote interface.
3. Target repositories (`axis-descriptor-lab`, `image-generator`) are mirrors plus proposal sources.
4. Manual edits in any repository are allowed and expected, but are treated as drift/proposals until reviewed.
5. Canonical writes must pass mud-server-compatible validation rules before apply/promotion.

## Action Semantics

1. `create`: canonical file exists and target is missing.
2. `update`: canonical and target both exist and differ.
3. `unchanged`: canonical and target match.
4. `target_only`: target file exists with no canonical file at same relative path.

`target_only` is informational drift classification by default. It is not an implicit delete instruction.

## Directionality

1. Outbound sync applies only canonical-to-target `create/update` actions.
2. `target_only` files are review candidates that can later become promotion or explicit cleanup decisions.
3. Default apply mode is non-destructive and never auto-deletes target files.

## UI Contract

1. Sync panel must communicate workflow explicitly: refresh -> verify -> apply.
2. Target-only items must render as neutral informational cards, not delete warnings by default.
3. Users must be able to compare and open canonical/target variants before decisions.
4. Reviewed counters and plan freshness state are required before apply decisions.

## API Contract

1. `/api/sync-plan` returns canonical-outbound and target-only classifications.
2. `/api/sync-apply` applies only non-destructive create/update actions.
3. `/api/sync-compare` remains the review surface for per-path source/target comparison.

## Hashing Contract

1. Policy Workbench uses `pipeworks-ipc` hashing helpers for deterministic file/content signatures.
2. Hashing is used for stable compare/equality semantics and future drift-baseline support.

## Near-Term Phase Plan

1. Phase 1: `delete_candidate` -> `target_only` reclassification and neutral UI tone.
2. Phase 2: baseline hash store for better drift directionality (`canonical_ahead`, `target_ahead`, `conflict`).
3. Phase 3: inbound proposal workflow (promote/reject/defer) with audit trail.
