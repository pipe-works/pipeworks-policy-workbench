# Policy Types

The workbench authors a fixed set of policy types against the canonical
mud-server policy API. They split cleanly into two layers based on whether
their content payload references other policies.

## Layered relationships

```{mermaid}
graph LR
    subgraph L1["Layer 1 — atomic content"]
        direction TB
        prompt["prompt<br/>text"]
        image_block["image_block<br/>text or object"]
        species_block["species_block<br/>YAML"]
        clothing_block["clothing_block<br/>structured object"]
        tone_profile["tone_profile<br/>JSON"]
    end

    subgraph L2["Layer 2 — composite"]
        direction TB
        descriptor_layer["descriptor_layer<br/>references[] + text"]
        registry["registry<br/>references[] only"]
    end

    L2 -. "references[].policy_id" .-> L1
```

Layer 2 types must include a non-empty `references[]` array of
`{policy_id, variant}` pairs that resolve to Layer 1 policies. Authoring
helpers in `policy_workbench.policy_authoring` validate and normalize these
references on save (`_normalize_reference_entries`).

## Layer 1 — atomic content

| Type | Content shape | Notes |
| --- | --- | --- |
| `prompt` | text or object with `text` field | Used by image generation prompts. Accepts free text or YAML/JSON with a `text` key. |
| `image_block` | text or object with `text` field | Reusable image-generation block snippets. Same text-or-object shape as `prompt`. |
| `species_block` | YAML structured | Canonical species block content under `image/blocks/species`. |
| `clothing_block` | structured object | Authored as YAML/JSON object content. |
| `tone_profile` | JSON object with `prompt_block` field | Strict JSON object payload; `prompt_block` must be a non-empty string and is the prompt-injectable text consumed by image-generator. The field name differs from other Layer 1 atomic types (which use `text`) to match the canonical mud-server schema and its renderer. |

## Layer 2 — composite

| Type | Content shape | Validation |
| --- | --- | --- |
| `descriptor_layer` | `{ references: [...], text: "..." }` | `text` must be non-empty; `references[]` must be a non-empty list of `{policy_id, variant}`. |
| `registry` | `{ references: [...] }` | `references[]` must be non-empty. Legacy registries with `entries`/`slots`/`block_path` fields are migrated by `_infer_registry_references_from_legacy_payload` when no explicit `references` are present. |

## Non-authorable types

The mud-server policy inventory may surface additional canonical types
(for example `axis_bundle` in `Pipeworks Web`) that are not authored
through this workbench. These appear in `/api/policies` listings and detail
views but the editor is read-only for them — `is_authorable` is `false` on
the inventory row, and `policy_workbench.static.workbench.inventory.policy_selector.AUTHORABLE_POLICY_TYPES`
gates which rows enable the Edit/Save controls.

The frontend list of authorable types lives in
`src/policy_workbench/static/workbench/inventory/policy_selector.js` and
the backend list lives in `policy_workbench.policy_authoring._build_save_content_payload`.
Both must be updated together when adding or removing an authorable type.
