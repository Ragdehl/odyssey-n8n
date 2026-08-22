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

## Phase 15.1 contract: schema-aware property changes

Architecture challenge result: **PROCEED**. The real problem is to preserve structured domain data
already declared by the canonical schema without making Phase 16 reinterpret user language and
without hard-coding current Odyssey types or field names. The simplest boundary is to keep the single
Sol/low interpretation call and add a small generic property-change representation whose allowed
fields and values are derived from `config/note-schema.json`.

### KnowledgeUnit extension

Phase 15.1 adds `properties` to every `KnowledgeUnit`. `properties` is an ordered list of generic
property changes, not a free-form metadata object:

```json
{
  "subject": "Marta",
  "type": "person",
  "intent": "record",
  "properties": [
    {
      "field": "birth_date",
      "op": "set",
      "value": "1990-05-03"
    },
    {
      "field": "relationship_to_user",
      "op": "set",
      "value": "hermana"
    }
  ],
  "facts": [],
  "references": []
}
```

A property removal is explicit and carries `null` only as the operation payload marker:

```json
{
  "subject": "Marta",
  "type": "person",
  "intent": "remove",
  "properties": [
    {
      "field": "birth_date",
      "op": "remove",
      "value": null
    }
  ],
  "facts": [],
  "references": []
}
```

The model-facing and production representation should correspond to an immutable generic value such
as `PropertyChange(field, op, value)`. `op` is deliberately limited to `set` and `remove` in Phase
15.1. Collection-item add/remove semantics are not introduced speculatively; if a future use case
needs partial mutation of an array property, extend the operation vocabulary then rather than hiding
that behavior inside `set`.

### Intent and payload rules

- `record` permits `set` property changes. It represents desired knowledge, not physical CREATE.
- `amend` permits `set` property changes. The value is the corrected desired value; the planner does
  not need to reproduce the previous stored value.
- `remove` permits `remove` property changes. `value` must be `null`; Phase 16 later decides whether
  the resolved note can legally lose that field.
- `delete` requires both `properties: []` and `facts: []`; whole-note deletion never travels through
  property changes.
- A field may occur at most once in one `KnowledgeUnit`. A correction is one `set`, not remove+set.
- `amend` and `remove` require at least one semantic payload across `properties` and `facts`.
- `record` requires at least one semantic payload across `properties` and `facts`, except for the
  already-approved reference-only record case where another unit references it.
- A fact fully represented by a canonical property should not be duplicated in `facts`. Any remaining
  information that the property does not capture stays as free text. For example, if only
  `birth_date` exists, `Marta nació el 3 de mayo de 1990 en Toulouse` becomes a `birth_date` property
  plus a free-text fact for the Toulouse information rather than duplicating the date in prose.

Required schema properties are **not** required on every Phase 15.1 unit. The planner does not know
whether the later physical result is CREATE or UPDATE, so requiring all create-time fields here would
reintroduce repository-state inference. The planner must extract a required property whenever the
request supplies it safely. Phase 16 must refuse or defer a CREATE whose final metadata cannot satisfy
the canonical schema. Likewise, removal of a required property can be represented semantically here
but cannot be persisted if it would leave an invalid note.

### Dynamic schema ownership — no hard-coded property registry

`config/note-schema.json` remains the only canonical registry of note types and type-specific
properties. Phase 15.1 must derive write capabilities dynamically, conceptually through a helper such
as `build_write_capabilities(schema)`. That projection should expose only information needed for
write interpretation: each canonical type's identity/description/examples and each
`types[].properties` definition's `id`, `value_type`, `required`, `description`, and relevant
constraints. Retrieval-only guidance is not a substitute for this write projection.

There must be no production branch such as `if type == "person"`, no list of known property IDs in a
prompt, and no separate per-application property registry. Adding a new canonical type or adding a
new property that uses an already-supported `value_type` must make it available to the planner and
local validator by changing the schema only.

The Phase 15.1 implementation must include a synthetic-schema test proving this. For example, a test
may add a temporary `car` type with a `registration_number` string property and verify that write
capabilities, Structured Outputs, and deterministic validation accept it without any production-code
change naming either `car` or `registration_number`.

### Supported value types and extension rule

Property values must be validated using the same canonical value semantics as persisted note
metadata; Phase 15.1 must not create a second, divergent validator. The currently supported schema
value types are `string`, `integer`, `array[string]`, and `date`. Dates remain strict `YYYY-MM-DD`
strings, integers exclude booleans, arrays contain strings, and declared constraints continue to
apply.

A **new property ID** or **new note type** using one of those supported value types requires no planner
code change. A genuinely **new `value_type`** is different: Odyssey must first add explicit support
for that type in the shared schema/value validation and Structured Outputs mapping, with tests. Until
then capability/schema construction must fail closed rather than silently treating an unknown type as
`string` or accepting an unvalidated value.

### Type scoping and writable surface

Phase 15.1 exposes only type-specific `types[].properties` as semantic properties. System/lifecycle
metadata such as `id`, `created_at`, `updated_at`, `created_by`, `updated_by`, `revision`, and
`schema_version` remains owned by persistence. `tags` remain deferred by product decision. `subtype`
and `aliases` are not added to this Phase 15.1 property contract.

A non-empty `properties` list requires a non-null canonical `KnowledgeUnit.type`, and every property
field must belong to that type in the active schema. `type=null` is still valid when classification is
unsafe, but such a unit cannot invent or infer type-specific properties.

### Deterministic validation boundary

The model output remains untrusted. Before returning a `RequestPlan`, local validation must verify at
least:

- the unit type is canonical when non-null;
- every property field exists under that exact type in the active schema;
- field names are unique within the unit;
- `set` carries a non-null value valid for the field's schema definition;
- `remove` carries `null`;
- property operations are compatible with the unit intent;
- `type=null` implies `properties: []`;
- the combined `facts` + `properties` payload obeys the intent rules above.

Structured Outputs should also be generated dynamically from the same schema to constrain the model,
but deterministic local validation remains authoritative. Unknown fields, unsupported value types,
wrong value shapes, cross-type properties, and malformed operations fail closed.

### Concept semantics required before the Phase 15.1 benchmark

The canonical `concept` description still contains historical fallback wording. Before freezing the
new benchmark prompt/schema, update the canonical schema so `concept` positively means a reusable,
identifiable abstract subject or topic that can accumulate knowledge across contexts, and explicitly
is not a generic fallback for underclassified statements. This ontology wording change has already
been approved as part of the Phase 15.1 design checkpoint.

### Phase 15.1 acceptance criteria added by this contract

- Existing Phase 15 retrieval/write behavior remains valid except where the extended contract
  intentionally moves canonical property information out of duplicate free-text facts.
- Sol/low receives dynamic write capabilities derived from the active schema in the same single
  interpretation call.
- Current properties such as `birth_date`, `relationship_to_user`, and `entry_date` can be emitted as
  validated structured property changes without hard-coded field logic.
- Synthetic new types/properties using existing supported value types work by schema change alone.
- Unsupported new value types fail closed until shared explicit support is added.
- `concept` is validated as a positive semantic type, not a fallback.
- A focused Sol/low benchmark covers property set/remove/amend behavior, required-property extraction,
  property-vs-fact separation, dynamic schema behavior, concept non-fallback behavior, and compact
  Phase 15 regression sentinels before Phase 16 implementation begins.
