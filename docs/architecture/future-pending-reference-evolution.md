# Future Pending-Reference Evolution

Status: **deferred product/architecture direction; revisit from real post-MVP pending-reference evidence**.

Pending references are durable evidence of work that could not be completed safely. They must not become an automatic ontology-growth or identity-authority mechanism.

## Two different recurrence signals

### Repeated unresolved entity

Repeated conservative exact/normalized mentions may justify proposing one canonical identity:

```text
Thales
Thales
Thales
   |
   v
"You refer to Thales repeatedly. Do you want Odyssey to create/resolve it as a canonical entity?"
```

Do not fuzzy-merge differently worded mentions merely because a model thinks they are similar. Known canonical aliases may participate only through the normal validated identity rules.

### Repeated not-yet-canonical semantic class

A future planner may preserve a bounded **advisory semantic type hint** for unresolved references, for example `organization`. Such a hint is not an Odyssey type and never authorizes creation/schema mutation.

If many **distinct** unresolved candidates repeatedly share one safely normalized hint, Odyssey may propose a useful schema/capability to the user.

```text
Thales / Airbus / Safran / ...
         |
normalized advisory hint: organization
         |
         v
schema-coach proposal explaining concrete benefit
         |
     user approval
         |
validated schema change / backfill contract
```

Do not choose a notification threshold before observing real frequency/noise/value. Do not count arbitrary free-form model labels directly: `company`, `empresa`, and `organization` are not deterministically equivalent without a bounded normalization/equivalence contract.

## Deterministic relinking

Future relinking must not ask a model to search arbitrary Markdown and decide what text to replace.

Odyssey already has stable note IDs and request-derived atomic fact locators. Pending evidence should retain or deterministically derive enough source address to identify the exact occurrence, conceptually:

```text
source_note_id
source_fact_locator = request_id:ordinal
local_reference_index
original mention / validated reference template
```

A safe relink is then:

```text
PendingReference
      |
      v
load authoritative current note by stable ID
      |
      v
parse exact Odyssey-owned fact/occurrence
      |
      +--> mismatch / removed / ambiguous -> leave pending / future HITL
      `--> exact safe occurrence
                 |
                 v
        newly resolved canonical target
                 |
                 v
 deterministic re-render of that occurrence
                 |
                 v
 revision + validation + request_id + Git + index refresh
```

A model may contribute bounded identity interpretation, but deterministic Core owns the physical mutation and validates the final target.

## Preserve original wording

The original mention is user wording and should remain available. If `Empresa Thales` later becomes a known alias of canonical `Thales`, rendering may preserve that display text in the wikilink. Without such evidence, Odyssey must not assume the two strings are the same identity.

One fact may contain several references. `local_reference_index` (or an equivalent deterministic occurrence address) must allow one resolved reference to be relinked without rewriting neighboring unresolved references/free text.

## User-facing proposal boundary

Keep entity and schema proposals separate:

```text
same unresolved identity repeats
  -> propose resolving/creating that entity

many distinct unresolved identities share one normalized advisory class
  -> propose a useful type/capability
```

Explain concrete value—stable identity, old-reference relinking, type-filtered retrieval, or app properties—rather than exposing ontology mechanics by default. The user explicitly approves canonical schema changes and any broad backfill operation.

## Guardrails

- no automatic canonical note creation from pending evidence;
- no automatic schema/type creation;
- no fuzzy identity merge solely from similar names;
- no arbitrary model-driven Markdown replacement;
- no relink unless the exact current source occurrence is addressable and matches expected evidence;
- zero safe candidates -> keep pending;
- multiple safe candidates -> keep pending / future HITL;
- exactly one safely established identity -> deterministic relink may proceed through normal safeguards;
- notification thresholds/cadence remain evidence-driven.

This direction builds on durable pending work and the adopted atomic-fact identity model. [Future Extension Points](future-extension-points.md) indexes it; this document is the detailed owner.
