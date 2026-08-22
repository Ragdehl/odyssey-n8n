# Phase 15 contract: write planning / knowledge preparation

Status: **COMPLETE / VALIDATED — deterministic preparation accepted; persistence remains out of scope**

## Objective

Extend request interpretation so one Sol/low planning response can represent existing retrieval work
and structured, semantic write knowledge suitable for a later identity-resolution and persistence
phase. This phase does not execute either kind of work.

```text
one user message
        |
        v
single Sol/low RequestPlan
   |                    |
RetrieveAction(s)   WriteAction -> KnowledgeUnit(s)
   |                    |
unchanged Phase 13     later Phase 16 resolution/persistence
```

## Acceptance criteria

- Existing `RetrieveAction` planning remains Phase 13-compatible; `get_context` is unchanged.
- A request can contain retrieval and write actions together.
- `WriteAction` groups facts for one logical subject only when their semantic intent is compatible,
  separates independent subjects or different intents, and preserves references between units.
- Each unit has a subject, optional canonical type, controlled semantic intent, intent-appropriate
  facts, and validated references.
- The only write intents are `record`, `amend`, `remove`, and `delete`.
- The planner does not resolve identity, infer repository existence, choose physical CREATE versus
  UPDATE, generate persistent IDs/paths/Markdown/SQLite rows, or execute persistence.
- All model output is validated deterministically and malformed output fails closed.
- No automatic mutation occurs.

## Out of scope

Entity-resolution execution; create/update/delete persistence; Markdown rewriting; `save_knowledge`;
`RequestPlan` execution/orchestration; n8n integration; HITL implementation; new ontology
infrastructure; and LangGraph, DAG, or workflow-engine infrastructure.

## Open decisions

None for the Phase 15 contract that was benchmarked and accepted. A post-merge pre-persistence review
subsequently identified a representation gap for canonical writable properties; that follow-up is
tracked as Phase 15.1 in the Functional Roadmap and does not invalidate the benchmark evidence below.

## Canonical contract

`RequestPlan.actions` is ordered and contains either the existing `RetrieveAction` or a `WriteAction`.
`WriteAction.units` is an ordered collection of semantic `KnowledgeUnit` values:

```json
{
  "kind": "write",
  "units": [
    {
      "subject": "Carrefour Balma",
      "type": "store",
      "intent": "amend",
      "facts": ["Closes at 20:30."],
      "references": []
    },
    {
      "subject": "Leche Pascual semidesnatada",
      "type": "product",
      "intent": "record",
      "facts": ["This is the user's habitual milk."],
      "references": []
    }
  ]
}
```

A reference is `{ "target_index": <unit index>, "role": <non-empty semantic role> }`. It is an
in-plan structural pointer, not a persistent identifier or relationship ontology. It must target a
different existing unit. `amend` and `remove` require at least one concrete fact. `delete` requires
`facts: []` and rejects any deletion prose. `record` normally requires facts, but permits
`facts: []` only when another unit in the same `WriteAction` references it as a semantic target.
`record` means remember knowledge and may later be resolved to an existing entity or a deliberately
approved new one. `amend`, `remove`, and `delete` require an existing target later; unresolved
identity never authorizes creation. This preserves the Phase 12 invariant
[`UNRESOLVED != CREATE`](../decisions/0005-phase-12-entity-persistence.md).

Facts for one logical subject are grouped only when their intent is compatible. For example, a
correction and a removal about Carrefour Balma are separate `KnowledgeUnit` values even though they
have the same subject. Later persistence may safely coalesce same-entity mutations; Phase 15 does not.

Semantic chronology such as “qué había pensado antes” remains in the retrieval query and does not
automatically become a `created_at` or `updated_at` filter. Explicit timing of when a note, entry, or
item was created, written, added, updated, modified, or recorded may still produce those filters.
Independent deterministic candidate sets remain independent `RetrieveAction` branches. A
write-target existence check is not a retrieval request: identity and existence are delegated to
the later Phase 9–11 resolution path, and `UNRESOLVED != CREATE` remains invariant.

Reference-only `record` units do not authorize creation merely because their identity is unresolved.
Phase 16 must decide creation authorization explicitly and safely.

The schema type, when supplied, must be one of the current canonical types. The action has no
persistence operation, entity ID, path, serialized Markdown, SQL, or storage instruction.

The experiment details and deterministic oracle are canonical in
[`benchmarks/phase15_write_planning/README.md`](../../benchmarks/phase15_write_planning/README.md).

## Validation record

The initial Structured Outputs compatibility attempt returned zero model outputs and is preserved
as failed harness evidence. The corrected full experiment completed 18 Sol/low calls. Human review
identified and corrected two planner-boundary issues: semantic “before” had become lifecycle
metadata, and a write-target existence check had become an unnecessary `RetrieveAction`.

The targeted follow-up completed five Sol/low calls: T01, T02, T03, and T05 were acceptable; T04
once collapsed the 1990/2000 OR into an unsatisfiable AND filter. One frozen-prompt T04 repeat
completed one additional Sol/low call and produced two independent candidate-set branches. Human
review accepts that isolated variance; no further paid calls are required. Raw evidence and exact
statuses remain unchanged under `benchmarks/phase15_write_planning/results/` and its `targeted/results/`
directories.

## Post-validation follow-up: why Phase 15.1 exists

The accepted Phase 15 output is sufficient to express semantic subjects, write intents, free-text
facts, and references, but it is not yet sufficient to materialize every canonical note correctly.
The canonical schema contains writable type-specific properties such as `person.birth_date`,
`person.relationship_to_user`, and required `journal_entry.entry_date`. If a request says
`Marta nació el 3 de mayo de 1990`, retaining that only as free-text would force a later phase to
reinterpret the original language before it could populate `birth_date`, and a required property such
as `entry_date` can make valid creation impossible if it is never extracted.

Phase 15.1 therefore extends, rather than replaces, this contract so the same Sol/low interpretation
call can infer canonical writable properties directly from the schema. The intended separation is:

```text
canonical property expressed by the request -> structured property value/operation
other useful knowledge                    -> free-text facts
```

This follow-up must not turn `concept` into a fallback classification. `concept` should mean a
reusable identifiable abstract subject with semantic identity of its own; if no type is safely
supported, `type=null` is preferable. Automatic tags remain deferred and are not part of Phase 15.1.

Phase 15.1 requires a new focused Sol/low validation because it changes the write output contract.
The existing Phase 15 raw evidence remains historical evidence for the contract above and must not be
rewritten retrospectively. See the canonical Functional Roadmap for the detailed Phase 15.1 decisions,
Phase 16 persistence decisions, and open questions discovered before implementation.
