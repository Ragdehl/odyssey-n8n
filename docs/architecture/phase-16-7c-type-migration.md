# Phase 16.7C type migration

Status: **implemented; deterministic verification and focused Sol/low planner validation passed**

This document is the canonical contract for Phase 16.7C. It replaces the earlier roadmap direction that suggested creating a new note and soft-deleting the old one.

## Objective

Allow an existing active Odyssey note to change canonical type without splitting identity, breaking existing wikilinks, silently losing metadata, or creating a second replacement entity.

A type migration changes the canonical representation of the **same logical entity**:

```text
existing active note
      |
      v
resolve one stable identity
      |
      v
build destination representation in memory
      |
      +--> invalid / lossy / incomplete -> NEEDS_CLARIFICATION, no write
      |
      `--> fully valid destination note
                |
                v
       revision-guarded atomic replacement
                |
                v
        same ID + same path + new type
```

The problem is not generic schema-migration infrastructure. It is safely changing the type-specific contract of one existing note while preserving Odyssey identity continuity.

## Identity continuity

A successful Phase 16.7C migration MUST preserve:

- the same stable `id`;
- the same Markdown path;
- the same canonical `name` unless the user separately requests a supported rename;
- the same `created_at` and `created_by` lifecycle metadata;
- existing inbound and outbound wikilinks;
- the note body unless an explicitly approved deterministic transformation is required.

The migration updates normal modification lifecycle metadata and increments `revision` once.

Phase 16.7C MUST NOT create a destination note with a new ID and then soft-delete the source note. That approach would split one logical identity and leave historical wikilinks pointing at the superseded object.

Because Odyssey filenames are stable physical labels and canonical identity is carried by `id`/`name`, a type migration does not rename or move the Markdown file merely because `type` changes.

## Planner representation

The production RequestPlan needs one explicit destination-type field for a single-note write migration.

Recommended bounded shape:

```text
KnowledgeUnit
  target: SelectionCriteria      # identifies the current existing note
  intent: amend
  destination_type: person       # null for ordinary writes
  properties: ...                # explicit destination-compatible changes only
  tag_changes: ...
  facts: ...
  references: ...
  cardinality: one
```

Contract:

- `destination_type` is nullable for ordinary existing behavior;
- when non-null it must be one canonical type from the active schema;
- it is emitted only when the user explicitly requests canonical type reassignment or clearly corrects the canonical classification of the same logical note;
- it must not be inferred merely because some prose resembles another type;
- source identity selection and destination type are separate concepts: `target.type`, when present, constrains the current source note; `destination_type` declares the requested resulting type;
- initial type migration supports only `cardinality=one`;
- `destination_type` is not a metadata property and must not be represented as `PropertyChange(field="type", ...)`;
- the planner still does not resolve identity, choose paths, mutate Markdown, or execute persistence.

This is a production Structured Outputs/prompt contract change, so focused live planner evidence plus compact historical regression sentinels are required under `AGENTS.md`. Do not rerun broad model selection.

## Destination-schema validation

A type migration is authorized only when Odyssey can build one complete destination note that validates under the active canonical schema before writing anything.

The migration algorithm is fail-closed:

```text
current metadata/body
      |
      v
apply requested destination type
      |
      v
apply explicit supported property/tag/body changes
      |
      v
check source-only metadata
      |
      +--> would become invalid -> NEEDS_CLARIFICATION
      |
      v
check destination required metadata
      |
      +--> missing -> NEEDS_CLARIFICATION
      |
      v
validate complete destination note
      |
      +--> invalid -> NEEDS_CLARIFICATION
      |
      `--> valid -> persist atomically
```

### No silent information loss

If the source note contains type-specific metadata that is not allowed by the destination type, Phase 16.7C MUST NOT silently discard it.

Example:

```yaml
name: Marta
type: person
birth_date: 1990-01-01
```

A migration to `project` cannot simply remove `birth_date`. The migration must fail closed unless a future explicitly approved migration policy defines how that information is preserved.

Initial Phase 16.7C does not convert incompatible structured properties into prose automatically.

### No invented required properties

If the destination type requires metadata that the resulting note does not have, Odyssey MUST NOT invent it.

Example:

```text
concept -> journal_entry
```

`journal_entry` requires `entry_date`. The migration may succeed only when the request already supplies a valid destination-compatible value through the approved planner/materialization contract. Otherwise it returns a typed clarification/unsupported outcome and performs no write.

### Destination-compatible explicit mutations

When `destination_type` is non-null, any property changes in the same KnowledgeUnit are validated against the destination type, not treated as arbitrary source-type mutations.

This allows a bounded migration such as:

```text
concept -> journal_entry
+ explicit entry_date supplied by the user
```

provided the complete destination note validates and no source-only metadata would be lost.

Do not broaden this into a generic migration DSL.

## Body behavior

Initial Phase 16.7C preserves the Markdown body exactly unless the same KnowledgeUnit already contains an ordinary supported explicit body mutation whose semantics are independently valid.

Changing type alone does not invoke the semantic UPDATE writer and does not rewrite prose merely to “fit” the destination type.

If a future migration genuinely requires semantic body restructuring, that must be separately justified and evidenced. It is not part of the initial contract.

## Persistence boundary

Type migration should use a dedicated Core persistence/materialization boundary rather than allowing ordinary `update_entity()` callers to mutate `type` freely.

Preferred behavior:

- load one validated active source note;
- require expected stable ID and revision;
- construct the full destination Note in memory;
- preserve protected identity/creation metadata;
- set the new canonical type;
- apply only explicitly authorized destination-compatible mutations;
- validate the whole destination Note;
- replace the same Markdown path once;
- increment `revision`, update `updated_at`/`updated_by`;
- return a typed persistence/materialization result.

No intermediate invalid Markdown may be written.

Ordinary update paths must remain unable to mutate Core-protected type migration state accidentally.

## Active/deleted boundary

Initial Phase 16.7C operates only on one resolved **active** note.

Deleted notes are not normal migration targets. Restore-then-migrate semantics are outside this phase.

A successful type migration does not set `deleted: true` and does not create a tombstone because the identity itself continues in place.

## References and wikilinks

Because stable ID, path, and canonical note identity remain continuous, existing inbound/outbound wikilinks do not need rewriting.

Phase 16.7C MUST NOT scan and mutate backlink source notes merely because the destination type changed.

Reference binding for ordinary facts remains governed by the existing Phase 16.5 contract. Type migration does not create a new identity for references to bind to.

## Cardinality

Initial type migration supports only:

```text
cardinality = one
```

`all_matching` type migration is out of scope. Bulk schema migration is materially more dangerous because incompatible source metadata and destination requirements can differ per note.

## Model usage

Runtime type migration materialization itself is deterministic and should make no new LLM call.

However, the RequestPlan production contract must be extended so Sol/low can represent an explicit `destination_type`. Therefore implementation must:

- make the smallest planner prompt/Structured Outputs change needed;
- preserve current planner model `gpt-5.6-sol` and low reasoning unless new evidence proves that impossible;
- run focused live cases for explicit type reassignment and non-migration controls;
- run compact historical sentinels proportional to the changed planner contract;
- avoid reopening model selection.

## Acceptance criteria

Phase 16.7C is complete when deterministic and required live evidence prove at least:

1. RequestPlan can represent an explicit canonical `destination_type` without overloading `target.type` or ordinary PropertyChange;
2. ordinary non-migration planner behavior remains unchanged when `destination_type=null`;
3. planner does not infer type reassignment from ordinary semantic similarity alone;
4. one resolved active note can migrate to a different canonical type while preserving stable ID and path;
5. `created_at`/`created_by`, canonical name, body, existing wikilinks, universal metadata, and compatible metadata are preserved unless separately and explicitly mutated;
6. revision/update lifecycle metadata changes exactly once on success;
7. the complete destination note is validated before persistence;
8. source-only type properties are never silently dropped;
9. missing destination-required properties are never invented;
10. explicit destination-compatible properties supplied in the same migration request may satisfy destination requirements;
11. failure/clarification performs zero writes;
12. deleted notes are not normal migration targets;
13. bulk/all-matching type migration remains unsupported;
14. no replacement entity/new stable ID is created;
15. no backlink rewriting is performed;
16. type migration materialization itself makes no LLM call;
17. focused Sol/low planner evidence and historical regression sentinels satisfy `AGENTS.md`;
18. full deterministic Odyssey verification passes.

## Out of scope

- create-new-then-soft-delete migration;
- stable-ID replacement or redirect tables;
- file/path rename caused only by type change;
- backlink rewriting;
- automatic conversion of incompatible structured properties into prose;
- semantic rewrite of the whole body solely because type changed;
- automatic invention of required destination metadata;
- deleted-note restore-and-migrate;
- bulk `all_matching` type migration;
- generic schema migration engine/DSL;
- schema-version migration framework;
- n8n/application orchestration;
- Phase 17 pending-work/HITL persistence.

## Open decisions

None required before implementation of the bounded Phase 16.7C slice.

Public class/function names and the exact typed clarification/error names remain implementation details as long as the fail-closed, identity-preserving boundaries above are maintained.

## Architecture challenge

**PROCEED with the revised architecture.**

The earlier roadmap approach (create a destination entity and soft-delete the source) adds avoidable identity continuity problems. The current Odyssey model already separates stable identity/path from canonical type, and persistence can validate a complete Note before atomically replacing the same Markdown path. Reusing that model is simpler and safer.

The minimum safe implementation is therefore an in-place, revision-guarded migration of the same entity. It preserves links automatically and fails closed whenever the destination schema would require information loss or invented data. No generic migration framework, redirect layer, backlink rewrite, or migration LLM is justified by the current problem.
