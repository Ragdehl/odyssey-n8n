# Phase 16.7A bulk UPDATE and explicit cardinality

Status: **implementation complete; deterministic verification passed; live Sol/low evidence unavailable**

This document is the canonical Phase 16.7A contract. It extends the already-validated Phase 15 write
planning and Phase 16 per-note UPDATE materialization boundaries with one explicit distinction the
current system cannot safely infer later: whether the user intends to mutate one existing note or all
existing notes in one deterministically bounded set.

## Objective

Preserve user-intended write cardinality in the Sol planner and execute explicitly authorized bulk
UPDATEs without turning semantic similarity or ambiguity into mutation authority.

```text
user request
    |
    v
Sol/low planner
    |
    +--> cardinality = one
    |       -> existing Phase 16.1 single-target resolution
    |
    `--> cardinality = all_matching
            -> deterministic type/filter set only
            -> existing notes only
            -> per-note guarded UPDATE materialization
```

The real problem is not adding a generic batch engine. The problem is preventing later Core code from
having to guess whether plural language such as "todas", "todos", "cada", "all", or an explicitly
bounded group means one target or a complete selected set.

## Planner contract

Phase 16.7A adds write cardinality to `KnowledgeUnit`, not to shared `SelectionCriteria`.
`SelectionCriteria` remains reusable by retrieval, write targeting, graph anchors, and delegation and
does not itself prescribe mutation cardinality.

Conceptually:

```text
KnowledgeUnit
├─ target: SelectionCriteria
├─ cardinality: one | all_matching
├─ intent: record | amend | remove | delete
├─ properties
├─ tag_changes
├─ facts
└─ references
```

### `one`

`one` preserves all current behavior. Phase 16.1 may use exact, semantic, and contextual identity
resolution, and ambiguity fails closed.

Examples:

```text
"Marta ahora vive en Lyon"
cardinality = one

"Quita el tag review de la entrada de diario del 27 de agosto"
cardinality = one
```

### `all_matching`

`all_matching` is emitted only when the user explicitly requests mutation of the complete set
represented by the deterministic selection.

Examples that can be represented safely with current capabilities:

```text
"Añade el tag review a todas las personas nacidas en 1990"
cardinality = all_matching
target.type = person
target.filters = birth_date >= 1990-01-01, birth_date < 1991-01-01

"Quita el tag idea de todas las entradas de diario de agosto"
cardinality = all_matching
target.type = journal_entry
target.filters = entry_date >= 2026-08-01, entry_date < 2026-09-01
```

The planner must not emit `all_matching` merely because a target description is plural. It must
preserve explicit user intent to mutate the whole selected set. If the user asks for one target but
selection could match several, cardinality remains `one` and existing ambiguity handling applies.

Explicit named independent targets may remain separate `KnowledgeUnit(cardinality=one)` values rather
than inventing an `EXACT_SET` cardinality in this phase.

## Safe bulk-selection boundary

Initial production bulk membership must be deterministic.

For `all_matching`:

- `target.entity` must be null;
- `target.link_scope` must be null;
- target selection must include at least a canonical `type` or one deterministic canonical filter;
- membership is computed from authoritative Markdown metadata using the existing schema/filter
  contract;
- semantic similarity, embeddings, contextual resolution, or the free-text `query` must not decide
  whether a note belongs to the mutated set;
- the human-readable query remains useful interpretation/audit context but is not mutation authority.

Therefore this is safe:

```text
"Añade el tag review a todas las personas nacidas en 1990"
    -> deterministic type + birth_date filters
```

and this is intentionally unsupported in the initial slice:

```text
"Actualiza todas las notas relacionadas con Odyssey"
    -> semantic membership only
    -> fail closed / unsupported bulk selection
```

Likewise graph-derived bulk membership remains out of scope until the graph executor exists.

This restriction is deliberate. False-positive semantic retrieval is acceptable for showing context;
it is not acceptable as autonomous authority to mutate many notes.

## Physical target decision

`all_matching` never authorizes CREATE.

Core resolves the complete authoritative ID set before starting mutation:

```text
deterministic target selection
        |
        +--> 0 matches -> EMPTY_SET / no writes
        |
        `--> N matches -> BULK_UPDATE(ids...)
```

A zero-match bulk request is not evidence that a new note should be created. It returns an explicit
empty-set result that the Phase 17 application boundary can present to the user.

Stable IDs are frozen for that execution attempt before per-note materialization begins. Each note is
still revision-guarded independently by the existing Phase 12/16 UPDATE path.

## Materialization

Phase 16.7A should reuse `materialize_update()` rather than introduce a second writer or a generic
transaction framework.

Conceptually:

```text
BULK_UPDATE(stable_ids)
        |
        v
for each stable_id in deterministic order
        |
        v
existing materialize_update()
        |
        +--> deterministic property/tag mutation
        +--> exact duplicate shortcut
        `--> Luna/medium only when that note needs semantic body reconciliation
```

The same planned mutation payload is applied independently to each selected existing note. Existing
single-note schema, link, exact-span, stable-ID, and revision protections remain authoritative.

Bulk UPDATE does not imply one LLM call for the whole set. If free-text reconciliation is required,
each authoritative note remains an independent bounded writer context. This preserves correctness but
means semantic bulk cost grows with the number of notes; Phase 17 may later add an explicit
confirmation/presentation step for expensive operations if real usage demonstrates the need.

## Result and partial success

Bulk UPDATE necessarily introduces a local multi-note result, but Phase 16.7A does not create a generic
cross-action workflow engine.

The result must preserve at least:

```text
BulkUpdateResult
├─ requested_cardinality = all_matching
├─ selected_note_ids
├─ succeeded results by stable ID
└─ failed results by stable ID + typed reason
```

Selected notes are independent targets. A failure updating one note does not imply that an already
successful update to another note should be rolled back. Phase 16.7A therefore reports per-note
success/failure explicitly rather than pretending filesystem writes across several notes are one
atomic transaction.

Durably recording failed/deferred work for later human treatment belongs to the Phase 17 application
boundary described below; Phase 16.7A returns enough structured evidence for that later boundary to
persist pending work without reconstructing the failed request.

## Reference restriction

The existing Phase 16.5 reference table assumes one physical identity/path per `KnowledgeUnit`.
An `all_matching` unit represents a set and therefore cannot safely occupy that identity role.

Initial Phase 16.7A rules:

- an `all_matching` unit must not contain `KnowledgeReference` values;
- another unit must not reference an `all_matching` unit;
- bulk writes involving graph/reference-set semantics are deferred to Phase 17 or a later focused
  extension.

This keeps Phase 16.5B/16.5C unchanged.

## Production planner evidence

This phase materially changes the production Sol planner prompt and Structured Outputs contract.
Therefore AGENTS.md requires focused live evidence using the same production planner:

```text
model: gpt-5.6-sol
reasoning: low
```

Do not rerun model selection. Add a small frozen cardinality benchmark that includes at least:

1. singular named update -> `one`;
2. singular contextual update with several possible candidates -> `one`, never bulk;
3. explicit `todas las personas nacidas en 1990` -> `all_matching` with deterministic filters;
4. explicit all notes of one canonical type -> `all_matching`;
5. plural wording that does not authorize the full set -> not `all_matching`;
6. explicit list of two/three named targets -> separate `one` units, not accidental all-matching;
7. semantic-only `todas las notas relacionadas con Odyssey` -> planner may preserve the request, but
   deterministic validation/execution must reject unsupported bulk membership;
8. regression cases for references, tags, properties, record/amend/remove/delete intent compatibility.

The implementation is in `odyssey_core/bulk_update.py`, with the frozen cases and runner in
`benchmarks/phase16_7a_cardinality/`. The deterministic suite passes. The live runner was attempted
with `gpt-5.6-sol`, low reasoning, `store=false`, and the production prompt/schema; the provider call
failed for all 11 cases, so no model behavior or token cost is claimed as validated. This phase is
not considered fully complete until that focused live evidence is available.

Deterministic tests remain required for schema and fail-closed behavior, but they do not replace this
focused production-model evidence.

## Neighboring decisions recorded for later phases

These decisions are intentionally recorded here so they are not lost, but they are not implemented by
16.7A.

### Phase 17 — durable pending work instead of silent partial failure

When a multi-unit or bulk operation cannot complete cleanly, the application boundary should preserve
all information necessary to process the unresolved work later. The preferred direction is a small
inspectable internal Markdown pending-work artifact, analogous to the already-planned pending-reference
HITL direction.

Until HITL exists, the artifact should retain the original normalized action, affected/failed stable
IDs, reasons, dependencies/candidates when relevant, and enough context to retry or resolve later.
This is workflow state, not automatically a canonical user-knowledge note type, and it must not be
silently indexed as ordinary knowledge.

### Phase 16.7B — soft delete

Whole-note DELETE should initially be soft deletion:

```text
deleted: true
```

Deleted notes remain physically present and recoverable but must be excluded by default from normal
retrieval, identity resolution, bulk selection, and structured calculations/aggregations. Implementing
this requires an explicit canonical schema proposal plus consistent index/query exclusion behavior;
that schema change is not part of 16.7A.

Inbound-link rewriting/deletion is not required for the initial soft-delete behavior because the note
continues to exist physically.

### Phase 16.7C — type change / migration

A type change should not be treated as an in-place metadata flip when the destination schema changes
the valid shape of the note. The current product direction is to treat it as a migration:

```text
old canonical note
    -> preserve/read complete authoritative content
    -> semantic rewrite for destination type/schema
    -> create destination representation
    -> soft-delete superseded representation only after successful creation
```

However, the exact identity/link architecture remains open. Creating a brand-new stable ID/path while
soft-deleting the old note would leave inbound wikilinks pointing to the superseded identity and could
split one logical entity into two identities. Before implementation, Phase 16.7C must explicitly decide
whether the migrated note preserves stable identity/path, uses a replacement/supersedes relation, or
rewrites inbound links. Do not implement delete+new-ID creation until that identity-continuity question
is resolved.

If semantic rewriting is selected, it must use an explicit bounded migration contract and focused live
evidence; it is not permission for routine whole-note rewrites elsewhere.

## Acceptance criteria

Phase 16.7A is complete when tests and focused live planner evidence prove at least:

1. `KnowledgeUnit` carries validated `one | all_matching` cardinality;
2. current singular planner cases remain `one`;
3. explicit deterministic-set bulk requests become `all_matching`;
4. `SelectionCriteria` remains unchanged and reusable;
5. `one` continues through current Phase 16.1 resolution unchanged;
6. `all_matching` cannot use semantic/contextual similarity as set membership authority;
7. `all_matching` requires deterministic type/filter scope and rejects entity/link-scope set selection;
8. zero matches performs zero writes and never CREATEs;
9. selected stable IDs are determined before mutation and processed deterministically;
10. each target reuses the existing guarded `materialize_update()` behavior;
11. structured bulk updates require no model call when the single-note path would require none;
12. free-text bulk updates use only the already-selected Luna-medium per-note UPDATE writer when needed;
13. one note failure is represented explicitly without hiding successful independent updates;
14. no rollback/transaction framework is introduced;
15. bulk units cannot participate in Phase 16.5 single-identity reference binding;
16. full deterministic verification passes and the focused Sol/low cardinality benchmark passes.

## Out of scope

- semantic-similarity-defined bulk membership;
- graph/link-scope bulk membership;
- automatic CREATE from an empty bulk set;
- exact-set cardinality abstraction when separate `one` units suffice;
- cross-unit dependency execution;
- durable pending-work persistence/HITL implementation;
- transactional rollback across notes;
- hard delete or inbound-link cleanup;
- soft-delete schema/index implementation;
- type migration implementation;
- RequestPlan application orchestration;
- n8n integration.

## Open decisions

None required before implementing Phase 16.7A. Per-note result class names and small API placement choices
are implementation details as long as the cardinality and fail-closed boundaries above remain intact.

## Architecture challenge

**PROCEED.** Bulk mutation is a demonstrated product requirement and the current planner explicitly
states that shared selection does not imply write cardinality. The smallest safe solution is to add
cardinality to `KnowledgeUnit`, preserve existing single-target resolution for `one`, and permit
`all_matching` only over deterministic schema/type/filter membership. Reusing existing per-note UPDATE
materialization avoids a batch framework or new writer. Semantic set membership, general dependency
orchestration, and durable HITL remain deferred because they would add authority and complexity not
needed to solve this phase.
