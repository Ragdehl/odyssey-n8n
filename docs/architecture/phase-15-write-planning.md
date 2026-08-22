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
call can infer canonical writable properties directly from the schema. During contract review a
second simplification was identified: write-target identification should reuse the same
`query`/`type`/`filters` selection vocabulary already used by `RetrieveAction.plan` instead of
inventing a write-only `subject` plus target-filter dialect.

The intended separation is:

```text
query/type/filters                         -> which note(s) fit the reference
canonical property expressed as a change -> structured property operation
other useful knowledge                    -> free-text facts
references                                -> links to other units in the same WriteAction
```

This follow-up must not turn `concept` into a fallback classification. `concept` should mean a
reusable identifiable abstract subject with semantic identity of its own; if no type is safely
supported, `type=null` is preferable. Automatic tags remain deferred and are not part of Phase 15.1.

Phase 15.1 requires a new focused Sol/low validation because it changes the write output contract.
The existing Phase 15 raw evidence remains historical evidence for the contract above and must not be
rewritten retrospectively. See the canonical Functional Roadmap for the detailed Phase 15.1 decisions,
Phase 16 persistence decisions, and open questions discovered before implementation.

## Phase 15.1 contract: schema-aware write targets and property changes

Architecture challenge result: **PROCEED**. The real problem is to preserve structured domain data
already declared by the canonical schema without making Phase 16 reinterpret user language, while
also preserving deterministic target-identification evidence instead of hiding it in free text. The
simplest boundary is to keep the single Sol/low interpretation call, reuse one selection contract, and
add a small generic property-change representation whose allowed fields and values are derived from
`config/note-schema.json`.

### KnowledgeUnit shape

Phase 15.1 intentionally replaces the Phase 15 write-unit `subject` plus top-level `type` fields with a
single `target` object. This is a forward contract refinement only; the historical Phase 15 benchmark
and evidence above remain unchanged.

```json
{
  "target": {
    "query": "Marta",
    "type": "person",
    "filters": []
  },
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
  "target": {
    "query": "Marta",
    "type": "person",
    "filters": []
  },
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

The model-facing and production representation should correspond to small immutable generic values,
conceptually `SelectionCriteria(query, type, filters)` and `PropertyChange(field, op, value)`. This
does not require introducing public abstractions solely for naming symmetry: implementation should
reuse the existing retrieval-plan builders/validators where practical and extract only the smallest
shared helper/value needed to avoid duplicate logic.

### One selection vocabulary: query, type, filters

`RetrieveAction.plan` and `KnowledgeUnit.target` use the same closed selection shape:

```text
query   non-empty semantic wording that should match candidate knowledge/identity
type    optional canonical type restriction
filters deterministic restrictions derived from the active retrieval/filter capabilities
```

They should share the same dynamic filter vocabulary, Structured Outputs construction, operator/value
rules, type compatibility checks, and deterministic filter validation. A new filterable property in
the canonical schema should therefore become available to both retrieval and write-target selection
without a write-specific code path.

The common shape does **not** mean a common executor or common cardinality rule:

```text
SelectionCriteria(query/type/filters)
             |
       +-----+-----+
       |           |
       v           v
RetrieveAction   KnowledgeUnit.target
       |           |
       v           v
get_context     existing-entity resolution
       |           |
       v           v
0..N results    one safe identity or abstain
for the user    (then separate record-create policy if applicable)
```

A write-target lookup is still not a user retrieval request and must not create an extra
`RetrieveAction`. Phase 16 may use the same filter semantics to restrict identity candidates before
Phase 11-style resolution, but it must not simply call `get_context`, pick the first match, or update
all matching notes.

`target.query` remains non-empty even when filters are strong. It carries the best identity-bearing
wording that is not safely represented by filters and, when the request gives a stable name, should
retain that name. This matters both for semantic resolution and for later creation policy. Filters are
only emitted when the user request maps explicitly and safely to the canonical filter contract; all
other target-identification meaning remains in `query`.

### Identification evidence is not mutation payload

`target.filters` answers **which note is being referred to**. `properties` and `facts` answer **what
knowledge should change**. A property mentioned only to identify the target must not be emitted as a
property mutation.

For example:

> Corrige la relación de la persona que nació el 3 de mayo de 1990: es mi hermana.

becomes conceptually:

```json
{
  "target": {
    "query": "la persona",
    "type": "person",
    "filters": [
      {"field": "birth_date", "op": "eq", "value": "1990-05-03"}
    ]
  },
  "intent": "amend",
  "properties": [
    {"field": "relationship_to_user", "op": "set", "value": "hermana"}
  ],
  "facts": [],
  "references": []
}
```

`birth_date` is selection evidence; it is not modified. Conversely, a request can legitimately use
the same field on both sides when it identifies the old value and supplies a corrected value. For
example, “corrige la persona nacida el 3 de mayo: nació el 4 de mayo” may use the old `birth_date` in
`target.filters` and a new `birth_date` `set` operation in `properties`. The planner must preserve that
distinction rather than deduplicating by field name across target and mutation.

When part of target identity is not filterable, `query` carries it. For “corrige a la amiga de Marta
nacida en 1990”, the relationship wording can remain in `query` while `birth_date` contributes safe
date filters. No second target-selection language is needed.

### Intent and payload rules

- `record` permits `set` property changes. It represents desired knowledge, not physical CREATE.
- `amend` permits `set` property changes. The value is the corrected desired value; the planner does
  not need to reproduce the previous stored value except when an old value is useful as target
  selection evidence.
- `remove` permits `remove` property changes. `value` must be `null`; Phase 16 later decides whether
  the resolved note can legally lose that field.
- `delete` requires both `properties: []` and `facts: []`; whole-note deletion never travels through
  property changes.
- A mutation field may occur at most once in `properties` for one `KnowledgeUnit`. A correction is one
  `set`, not remove+set.
- `amend` and `remove` require at least one semantic mutation payload across `properties` and `facts`.
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

### References remain in-plan logical links

`references` retains the accepted Phase 15 meaning: a reference is
`{ "target_index": <unit index>, "role": <non-empty semantic role> }` and points to another
`KnowledgeUnit` in the same `WriteAction`. It does not contain a persistent note ID or Markdown link.
Phase 16 first resolves or creates the referenced unit safely, then uses the resulting stable
identity/path to materialize the actual link. Reference-only `record` units remain allowed only when
another unit points to them; that allowance does not itself authorize creation.

### Dynamic schema ownership — no hard-coded property registry

`config/note-schema.json` remains the only canonical registry of note types and type-specific
properties. Phase 15.1 must derive write capabilities dynamically, conceptually through a helper such
as `build_write_capabilities(schema)`. That projection should expose only information needed for
write interpretation: each canonical type's identity/description/examples and each
`types[].properties` definition's `id`, `value_type`, `required`, `description`, and relevant
constraints. Retrieval-only guidance is not a substitute for this write projection.

Selection capabilities remain derived from the existing retrieval/filter projection. Write
capabilities and selection capabilities are different **views** of the same canonical schema, not two
registries: a property may be writable even when it is not filterable, while a filterable property can
appear in both retrieval filters and `KnowledgeUnit.target.filters`.

There must be no production branch such as `if type == "person"`, no list of known property IDs in a
prompt, and no separate per-application property registry. Adding a new canonical type or adding a
new property that uses an already-supported `value_type` must make it available to the write planner
and local validator by changing the schema only. If the property is also `filterable`, it must become
available to the shared selection/filter contract automatically as well.

The Phase 15.1 implementation must include synthetic-schema tests proving both paths. For example, a
test may add a temporary `car` type with a `registration_number` string property and verify that write
capabilities, Structured Outputs, and deterministic validation accept it without any production-code
change naming either `car` or `registration_number`; marking that property filterable should also
expose it through the common filter contract without a write-specific branch.

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
and `aliases` are not added to this Phase 15.1 property-mutation contract.

A non-empty `properties` list requires a non-null canonical `target.type`, and every mutation field
must belong to that type in the active schema. `target.type=null` is still valid when classification
is unsafe, but such a unit cannot invent or infer type-specific property mutations. Target filters
continue to obey their own existing capability/type-compatibility rules.

### Deterministic validation boundary

The model output remains untrusted. Before returning a `RequestPlan`, local validation must verify at
least:

- `target` has exactly non-empty `query`, optional canonical `type`, and a `filters` list;
- target filters pass the same dynamic field/operator/value/type-compatibility validation as retrieval
  filters;
- the target type is canonical when non-null;
- every property mutation field exists under that exact target type in the active schema;
- mutation field names are unique within the unit;
- `set` carries a non-null value valid for the field's schema definition;
- `remove` carries `null`;
- property operations are compatible with the unit intent;
- `target.type=null` implies `properties: []`;
- the combined `facts` + `properties` mutation payload obeys the intent rules above;
- reference indexes and roles retain the existing Phase 15 validation rules.

Structured Outputs should also be generated dynamically from the same schema to constrain the model,
but deterministic local validation remains authoritative. Unknown fields, unsupported value types,
wrong value shapes, cross-type properties, malformed operations, and invalid target filters fail
closed.

### Phase 16 boundary created by target filters

The current Phase 11 production resolver accepts semantic reference/context plus an optional type, but
not arbitrary structured filters. Phase 15.1 does **not** change that resolver or execute target
selection. Phase 16 must add the smallest bridge that applies validated target filters to candidate
selection before the existing identity decision path, while preserving the resolver's abstention
behavior.

Important invariants remain:

- filters narrow candidate evidence; they do not authorize a mutation;
- zero matching candidates is unresolved, not proof that creation is safe;
- multiple matching candidates are not bulk-update targets and must still be resolved or reported as
  ambiguous;
- `amend`, `remove`, and `delete` never create because selection failed;
- `record` creation remains governed by the separate Phase 16 creation policy.

Do not build a generic query engine or force `get_context` to become the identity resolver merely to
reuse syntax. Reuse the contract and deterministic validation; reuse execution code only where the
semantics genuinely match.

### Concept semantics required before the Phase 15.1 benchmark

The canonical `concept` description still contains historical fallback wording. Before freezing the
new benchmark prompt/schema, update the canonical schema so `concept` positively means a reusable,
identifiable abstract subject or topic that can accumulate knowledge across contexts, and explicitly
is not a generic fallback for underclassified statements. This ontology wording change has already
been approved as part of the Phase 15.1 design checkpoint.

### Phase 15.1 acceptance criteria added by this contract

- Existing historical Phase 15 evidence remains unchanged; Phase 15.1 intentionally refines the
  write-unit shape to `target + intent + properties + facts + references`.
- `RetrieveAction.plan` and `KnowledgeUnit.target` share one dynamic `query`/`type`/`filters` contract
  and one deterministic filter-validation path, without conflating their execution semantics.
- A filterable property mentioned only to identify a write target is emitted in `target.filters`, not
  as a mutation; non-filterable identity wording remains in `target.query`.
- The same property may safely appear as old target evidence and a new mutation value when the user is
  explicitly correcting that property.
- Sol/low receives dynamic write capabilities derived from the active schema in the same single
  interpretation call.
- Current properties such as `birth_date`, `relationship_to_user`, and `entry_date` can be emitted as
  validated structured property changes without hard-coded field logic.
- Synthetic new types/properties using existing supported value types work by schema change alone;
  filterable additions also flow automatically into both retrieval and write-target filters.
- Unsupported new value types fail closed until shared explicit support is added.
- `concept` is validated as a positive semantic type, not a fallback.
- A focused Sol/low benchmark covers property set/remove/amend behavior, required-property extraction,
  target-filter-versus-mutation separation, query-plus-filter target selection, property-vs-fact
  separation, dynamic schema behavior, concept non-fallback behavior, and compact Phase 15 regression
  sentinels before Phase 16 implementation begins.

### Phase 15.1 benchmark evidence — 2026-08-22

The independent focused evidence lives in
[`benchmarks/phase15_1_schema_write_planning/`](../../benchmarks/phase15_1_schema_write_planning/).
It uses the production `render_request_planner_prompt` and `request_plan_json_schema` functions,
`gpt-5.6-sol` with low reasoning effort, `store=false`, fixed per-case current context, the canonical
schema digest, and a synthetic `car.registration_number` schema extension. Every call preserves its
complete input, effective schema/capabilities, raw model output, local validation, oracle result, and
available usage immediately after the call; it does not alter Phase 15 historical evidence.

The full 15-call Sol/low pass produced 13 PASS, P09 FAIL, and P05 INVALID. P09's erroneous
`journal_entry` inference from a transient “hoy” reflection was a real prompt defect; the prompt was
clarified, a deterministic test was added, and its one-call follow-up passed. P05 remains INVALID:
“Corrige a la amiga de Marta nacida en 1990” provides target-selection evidence but no fact or
property to amend. A valid `amend` cannot be a no-op, and adding a fact/property would invent a
mutation; this is an unresolved input/contract boundary rather than a reason to weaken validation.

The benchmark is therefore **not accepted** and Phase 15.1 remains the current functional phase.
The 17 network-reachable calls (15 full plus the two-case explicit follow-up) reported an estimated
$0.227823 USD from the frozen pricing snapshot. A sandbox-only failed attempt is retained as separate
zero-token connection-error harness evidence. No Phase 16 work is authorized by this result.
