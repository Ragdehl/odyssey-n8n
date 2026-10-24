# Future Pending-Reference Evolution

Status: **partial active mechanism for genuinely unresolved current references; speculative future-type prediction explicitly not adopted (2026-10-24)**.

A `PendingReference` records an actual reference-resolution failure in current work; durability depends on the outer pending-work boundary and is **not** automatic for every literal mention. Keep genuine unresolved identity/reference handling. It must not become an ontology-growth or identity-authority mechanism. New-type candidate discovery runs **when the user creates the type**, scanning the canonical facts; no speculative classification of future types during ordinary capture. See [Conversational schema design](post-ui2-note-creation-and-schema-evolution.md#contrato-de-implementación-acordado-para-la-siguiente-fase-24-10-2026).

## Genuine unresolved identities and the retired speculative idea

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

### Unadopted historical idea: guessing future types

The earlier proposal to collect advisory labels such as `organization`,
normalize their recurrence, and notify the user about not-yet-defined types is
**not part of the approved roadmap**. It was speculative work before any user
created that type, with potentially unbounded overhead and no clear payoff.
Do not implement or revive that pipeline without a new observed product need
and explicit design approval. When a new type is confirmed, inspect existing
canonical facts on demand; pending references from real failed resolutions may
be consulted but are neither required nor exhaustive.

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

The original mention is user wording and should remain available for clarification/audit, but once a target is resolved the durable wikilink display uses the canonical note name. If `Empresa Thales` later becomes a known alias of canonical `Thales`, alias evidence may help resolution, but rendering still uses `Thales`; Odyssey never promotes occurrence wording into durable alias text implicitly.

One fact may contain several references. `local_reference_index` (or an equivalent deterministic occurrence address) must allow one resolved reference to be relinked without rewriting neighboring unresolved references/free text.

## User-facing proposal boundary

Repeated unresolved identities may still justify a **specific clarification**
of an entity that the user actually tried to reference. They do **not** trigger
new type proposals, background classification, or automatic note creation.
Creation of a type is a separately approved user request. After that request,
a dedicated on-demand scan of canonical facts may propose candidate entities;
Core verifies stable identity and exact source evidence before any authorized
write or relink.

## Guardrails

- no automatic canonical note creation from pending evidence;
- no automatic schema/type creation;
- no fuzzy identity merge solely from similar names;
- no arbitrary model-driven Markdown replacement;
- no relink unless the exact current source occurrence is addressable and matches expected evidence;
- zero safe candidates -> keep pending;
- multiple safe candidates -> keep pending / future HITL;
- exactly one safely established identity -> deterministic relink may proceed through normal safeguards;
- do not classify future semantic classes or schedule speculative notifications;
- on-demand scans and relinking must preserve canonical source evidence and user approval.

This deferred relinking direction builds on existing pending-work and atomic-fact identity contracts; it does not assert that every reference occurrence is durably indexed. [Future Extension Points](future-extension-points.md) indexes it; this document is the detailed owner.
