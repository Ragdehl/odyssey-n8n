# Future pending-reference evolution

Status: **future product/architecture direction; not a Phase 18 implementation requirement**

## Purpose

Preserve two related but distinct future capabilities built from durable unresolved references:

1. detect when the **same unresolved entity candidate** appears repeatedly and offer to create/resolve that canonical entity;
2. detect when **many distinct unresolved entity candidates appear to share the same not-yet-canonical semantic type** and offer to add a useful Odyssey type/capability.

These are proposals to the user, never automatic ontology growth or identity authority.

## Current boundary

Today a pending reference preserves the original validated `WriteAction` and execution evidence. The reference intent includes the original `mention`, semantic `role`, target unit, and any unresolved/candidate evidence. The target unit may contain a canonical `type` only when that type already exists in the current schema.

Therefore current evidence such as:

```text
mention = "Thales"
role = "employer"
target.type = null
```

does **not** mean Odyssey currently knows that Thales is an organization. `role` and canonical note `type` are different concepts.

## Two independent recurrence signals

### A. Repeated unresolved entity candidate

Repeated exact/normalized unresolved mentions may justify an entity proposal even when no new schema type is needed:

```text
Thales
Thales
Thales
Thales
    |
    v
proposal: "You refer to Thales frequently. Do you want to create/resolve it as a canonical Odyssey entity?"
```

The first safe implementation should group only evidence that can be joined deterministically, such as conservative normalized exact mention or an already-authorized canonical alias. Do not fuzzy-merge `Thales` and `Empresa Thales` merely because they look similar.

### B. Repeated not-yet-canonical semantic type

A future planner contract may optionally preserve an **advisory semantic type hint** for unresolved target entities, conceptually:

```text
mention = "Thales"
semantic_type_hint = "organization"
```

This hint is **not** a canonical Odyssey type, does not authorize note creation, and must never silently extend `config/note-schema.json`.

If many **distinct** unresolved entity candidates accumulate under the same validated/normalized hint, deterministic aggregation can surface a schema-coach proposal:

```text
organization-like pending candidates
├─ Thales
├─ Airbus
├─ Safran
├─ Capgemini
└─ OpenAI
        |
        v
proposal to user:
"You have several recurring entities of this kind. Adding a canonical type could let Odyssey create stable identities, relink old references, and support type-specific retrieval/properties. Do you want to add it?"
```

Do not choose a fixed notification threshold now. First collect real usage evidence, then define a threshold from observed frequency, number of distinct candidates, usefulness, and notification noise.

### Stable hint normalization is required before deterministic counting

Do not count arbitrary free-form model labels directly. Values such as `company`, `empresa`, and `organization` cannot be assumed to be the same merely because a model produced them on different days.

Before this feature is implemented, define the smallest stable hint-normalization contract. Safe options include a bounded advisory vocabulary, a stable proposal/hint registry, or explicit human-approved equivalence. Core must validate the resulting normalized key before it participates in deterministic counts.

Unknown or differently named hints may remain separate rather than being semantically merged by an unbounded model call. A type hint is evidence for a **proposal**, never identity or schema authority.

## Deterministic future relinking

Future relinking should not ask an LLM to search a Markdown note and decide which text to replace.

Odyssey already gives its own atomic facts a request-derived locator (`request_id + ordinal`) and notes have stable IDs. Future pending state must therefore retain or deterministically derive enough source-address information to identify the exact persisted fact and reference occurrence, conceptually:

```text
source_note_id
source_fact_locator = request_id:ordinal
local_reference_index
original mention
original marker-bearing fact/template from the validated WriteAction
```

Prefer derivation from already-durable request/action evidence where it is unambiguous rather than duplicating metadata unnecessarily. The requirement is **exact deterministic addressability**, not a specific storage field layout.

A safe relink can then be:

```text
PendingReference
      |
      +--> source stable note ID
      +--> exact atomic fact locator
      +--> local reference index
      |
      v
parse authoritative current Markdown
      |
      v
locate exactly that Odyssey-owned atomic fact
      |
      v
verify current fact still matches the expected plain rendered form
      |
      +--> mismatch / removed / ambiguous -> do not edit; keep pending or future HITL
      |
      `--> exact safe match
              |
              v
re-render the original validated marker occurrence using the newly resolved canonical target
              |
              v
normal revision + validation + request_id + Git + index-refresh safeguards
```

This keeps the physical Markdown edit deterministic. A model may have helped interpret the original request or may later help resolve ambiguous identity, but it does not receive authority to rewrite arbitrary note text.

## Preserve original wording and display text

The original `mention` is user wording and should remain available even after canonical identity resolution.

Example:

```text
canonical entity: Thales
pending mention: "Empresa Thales"
```

If `Empresa Thales` is later an explicitly known alias of canonical `Thales`, deterministic rendering may create a wikilink whose display preserves the original mention.

Without such evidence, Odyssey must not assume:

```text
"Thales" == "Empresa Thales"
```

Safe identity levels are:

1. conservative exact/normalized canonical name match;
2. exact known alias match;
3. otherwise unresolved/ambiguous -> keep pending or future HITL.

A semantic type hint alone must never merge two candidate identities.

## Several references inside one fact

The local reference index must continue to identify the exact marker occurrence even when one atomic fact contains multiple semantic references. Conceptually:

```text
original validated template:
"Marta dejó {{ref:0}} y empezó en {{ref:1}}."

ref:0 -> Airbus
ref:1 -> Thales
```

If only Thales becomes safely resolvable, Core can deterministically re-render only `ref:1` while preserving the other plain mention/pending intent. No free-text search-and-replace or LLM rewrite is required.

## User-facing schema coach

The two recurrence signals should remain separate because they imply different actions:

```text
same unresolved entity appears repeatedly
        -> propose creating/resolving THAT ENTITY

many distinct unresolved entities share one normalized semantic_type_hint
        -> propose adding THAT TYPE/CAPABILITY
```

A proposal should explain concrete benefits, for example stable identity, old-reference relinking, type-filtered retrieval, or type-specific properties. The user explicitly approves any canonical type/schema change and any bulk/backfill operation.

## Guardrails

- no automatic canonical note creation from pending evidence;
- no automatic schema/type creation;
- no fuzzy identity merge solely from similar names;
- no model-driven arbitrary Markdown replacement;
- no relink unless the exact source fact/reference occurrence is still safely addressable;
- no type-hint count until the hint key has passed a stable normalization/validation contract;
- zero safe identity candidates -> leave pending open;
- multiple safe identity candidates -> leave pending open / future HITL;
- exactly one safely established identity -> deterministic relink may proceed through normal mutation safeguards;
- thresholds and notification cadence remain future evidence-driven product decisions.

## Relationship to other future work

This direction extends:

- Phase 17B durable pending work;
- the pending-reference relinking direction in `future-extension-points.md`;
- the Functional Roadmap's emergent schema coach;
- future HITL/notification UX.

It does not require implementation during Phase 18. The first real E2E only needs to preserve enough durable evidence so these later capabilities remain possible.
