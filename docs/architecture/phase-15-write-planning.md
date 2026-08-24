# Phase 15 planning contract

Status: **Phase 15 through 15.3 accepted; Phase 16 is next**

This file is the canonical architecture contract for Phase 15 and its 15.1–15.3 refinements. Historical
benchmark inputs and raw model outputs remain append-only in their benchmark directories; the
Functional Roadmap records phase order and status without duplicating this contract.

## Objective

One Sol/low interpretation call turns an unstructured user message into an ordered, validated
`RequestPlan` without reading or mutating the vault.

```text
user message
    |
    v
single Sol/low planner
    |
    +--> RetrieveAction(s)
    +--> WriteAction(s) -> KnowledgeUnit(s)
    `--> DelegateAction(s)

execution, identity resolution, Markdown mutation and persistence happen later
```

The planner preserves semantic information that would otherwise need to be inferred again later, but
it does not resolve repository identity, infer note existence, choose physical CREATE versus UPDATE,
allocate IDs/paths, rewrite Markdown, execute graph traversal, run SQL, or persist data.

## Evolution of the contract

### Phase 15 — semantic write preparation

Phase 15 added ordered `WriteAction` values beside existing retrieval actions. A write is split into
logical `KnowledgeUnit` values with one target intent each. The only write intents are:

- `record`
- `amend`
- `remove`
- `delete`

`record` means desired knowledge and does not itself authorize physical creation. `amend`, `remove`,
and `delete` require an existing target later. `UNRESOLVED != CREATE` remains an invariant.

References between units remain logical in-plan pointers. They are not persistent IDs or a typed
relationship ontology; Phase 16 later materializes ordinary Markdown `[[wikilinks]]` after the
referenced identities are safe.

### Phase 15.1 — schema-aware properties and shared selection

Phase 15.1 replaced write-only `subject` selection with the same schema-driven `query` / `type` /
`filters` selection vocabulary used by retrieval and added canonical property mutations.

```text
selection evidence                         -> target
canonical writable field requested change -> properties
remaining knowledge                        -> facts
in-plan links                              -> references
```

A property used only to identify the target belongs in `target.filters`, not in the mutation payload.
The same field may legitimately appear as old selection evidence and as a new mutation value when the
user is correcting it.

`KnowledgeUnit.properties` uses generic changes:

```text
PropertyChange
├─ field
├─ op: set | remove
└─ value
```

`set` carries a schema-valid value. `remove` carries `null`. Property support is schema-driven from
`config/note-schema.json`; adding a new type/property that uses an already-supported value type must
not require a production branch naming that type or field. Unknown value types fail closed until
shared validation and Structured Outputs support exist.

`concept` is a positive semantic type for a reusable identifiable abstraction, never a fallback for
underclassified text. `journal_entry` is valid for a dated personal experience/reflection/occurrence.

### Phase 15.2 — explicit identity anchors, graph intent and explicit tags

Phase 15.2 preserves three pieces of meaning that the same Sol call can already understand and that
later execution should not have to reinterpret:

1. an explicit nominal target anchor (`entity`);
2. an explicit request to traverse wikilink relationships (`link_scope`);
3. an explicit user-requested tag restriction or tag change.

Phase 15.2 still does not execute any of those operations.

## Current shared selection contract

`RetrieveAction.plan` and `KnowledgeUnit.target` share the same closed selection shape:

```text
SelectionCriteria
├─ entity: str | null
├─ query: str
├─ type: str | null
├─ filters: ContextFilter[]
└─ link_scope: LinkScope | null
```

Sharing the value does not imply a shared executor or cardinality rule. Retrieval may return zero to
many notes for the user. A write target must later resolve to one safe identity or abstain.

### `entity`

`entity` is an unresolved nominal anchor extracted from the user request. It may be a primary-name or
alias candidate; it is not a stable Odyssey ID and does not assert that the note exists.

Examples:

```text
"Marta es mi hermana"
entity = "Marta"
query  = "Marta"

"Carrefour Balma cierra a las 20:30"
entity = "Carrefour Balma"
query  = "Carrefour Balma"

"¿Qué sé de n8n?"
entity = "n8n"
query  = "n8n"
```

The planner must not promote every mentioned entity or every noun phrase to `entity`:

```text
"Corrige a la amiga de Marta nacida en 1990: ahora vive en Lyon"
entity = null
query  = "amiga de Marta"
type   = person
filters = birth_date >= 1990-01-01 and birth_date < 1991-01-01
```

`Marta` is context, not the target. Likewise `la tienda de la esquina` is a contextual description,
not automatically a canonical name. When unsure, `entity=null` and the identifying meaning remains in
`query`.

Information already represented as a mutation stays outside target wording. For `Marta es mi hermana`,
`relationship_to_user=hermana` is the property mutation; the target query need not contain the
mutation prose.

### Type and filters

`type` is an optional canonical note-type restriction and must be used only when safely supported by
the canonical schema. Filters are deterministic restrictions derived from active schema capabilities.

Selection filters and write capabilities are different projections of the same canonical schema:

- a writable property may be non-filterable;
- a filterable property is available to retrieval and write-target selection automatically;
- unknown fields/operators/value shapes fail closed;
- a write property field requires a compatible non-null target type.

Lifecycle dates (`created_at`, `updated_at`) remain distinct from domain dates such as
`journal_entry.entry_date` or `person.birth_date`.

## Link scope: explicit graph traversal intent

`link_scope=null` means **do not traverse related notes**.

Therefore:

```text
"¿Qué sé de Marta?"
```

means the note representing Marta, not every note in the vault that mentions or links to Marta.

When the user explicitly asks for related/linked knowledge, the graph anchor reuses the same note
selection vocabulary without recursive link scopes:

```text
NoteSelector
├─ entity: str | null
├─ query: str
├─ type: str | null
└─ filters: ContextFilter[]

LinkScope
├─ anchor: NoteSelector
├─ direction: incoming | outgoing | both
└─ max_depth: integer >= 1
```

`NoteSelector` deliberately has no nested `link_scope`. The outer `SelectionCriteria` describes the
result notes wanted by the user; `link_scope.anchor` independently identifies the note to which those
results must be connected.

For now the anchor must resolve to one safe note identity. Ambiguous anchors fail closed/remain
pending rather than unioning arbitrary candidates. Set-valued graph joins are deferred until a real
case requires them.

Examples:

```text
"¿Qué notas están directamente relacionadas con Marta?"

outer query = "notas relacionadas con Marta"
link_scope.anchor = entity/query "Marta", type person
link_scope.direction = both
link_scope.max_depth = 1
```

```text
"¿En qué notas aparece la persona nacida el 3 de mayo de 1990?"

link_scope.anchor:
  entity = null
  query = "persona nacida el 3 de mayo de 1990"
  type = person
  filters = birth_date eq 1990-05-03

direction = incoming
```

Result restrictions and anchor restrictions are independent:

```text
"¿Qué entradas de diario de junio están relacionadas con la persona nacida el 3 de mayo de 1990?"

outer selection:
  type = journal_entry
  filters = entry_date >= 2026-06-01 and entry_date < 2026-07-01

link_scope.anchor:
  type = person
  filters = birth_date eq 1990-05-03
```

A phrase such as `esta nota` may remain semantic anchor wording, but later execution must not guess its
identity unless the calling interface supplies current-note context.

A requested depth greater than the future executor supports must fail explicitly rather than silently
changing the user's requested scope.

## Tags: explicit-only transversal labels

Tags remain canonical `array[string]` metadata, but the planner must never infer a tag merely from
semantic wording.

```text
"Busca ideas sobre Odyssey"
    -> no tag filter

"Busca notas con el tag idea"
    -> explicit tags contains "idea" filter is allowed

"Apunta esta idea"
    -> no automatic tag mutation

"Apunta esto y añade el tag review"
    -> explicit tag add is allowed
```

This safety rule applies to direct retrieval, write-target selection, graph anchors, and writes.

For selection, reuse the deterministic filter contract:

```text
ContextFilter(field="tags", op="contains", value=<controlled tag id>)
```

For writes, do not replace the complete tags array because the planner does not know every existing
tag. Use item-level changes:

```text
TagChange
├─ op: add | remove
└─ value: controlled_tag_id
```

`KnowledgeUnit.tag_changes` is ordered and contains only explicit user-requested operations. Unknown
tag IDs remain unsupported under the current controlled registry; Phase 15.2 does not silently create
new tags.

The current tag vocabulary remains unchanged by this phase. Whether values such as `idea` should later
become note types, or whether user-extensible transversal tags such as `familia`, `trabajo`, `casa`,
`finanzas`, or `viajes` should be added, is a separate ontology decision. A tag is an axis independent
of note type; it need not apply to every type, only to multiple types without redefining what the note
is. Structured behavior such as task status/priority or access permissions should not be modeled as a
tag merely for convenience.

## Current KnowledgeUnit shape

Conceptually:

```text
KnowledgeUnit
├─ target: SelectionCriteria
├─ intent: record | amend | remove | delete
├─ properties: PropertyChange[]
├─ tag_changes: TagChange[]
├─ facts: str[]
└─ references: Reference[]
```

Rules:

- `record` and `amend` may carry `set` property changes and explicit tag changes.
- `remove` may carry property removals, fact removals, and explicit tag removals as appropriate.
- `delete` carries no property/fact/tag mutation payload; it is whole-note intent.
- `amend`/`remove` require at least one semantic mutation payload.
- `record` requires useful knowledge unless it is the already-approved reference-only unit case.
- a canonical property fully representing a fact should not be duplicated in free text;
- information not safely represented by a canonical property remains in `facts`;
- required properties are extracted when supplied, but the planner does not know whether persistence
  will CREATE or UPDATE; Phase 16 must refuse/defer a CREATE whose final note cannot satisfy schema.

## Deterministic validation boundary

All model output is untrusted. Before returning `RequestPlan`, local validation must enforce the
active schema/contract, including:

- closed action and value shapes;
- non-empty semantic queries;
- canonical type IDs when non-null;
- valid field/operator/value/type-compatible filters;
- `entity` nullable but non-empty when present;
- non-recursive `NoteSelector` graph anchors;
- supported link direction and positive bounded depth representation;
- canonical property fields for the exact target type;
- valid set/remove property operations and unique mutation fields;
- explicit-only tag evidence plus controlled tag IDs;
- valid tag add/remove operations without whole-array replacement;
- intent/payload compatibility;
- valid reference indexes/roles;
- no repository IDs, paths, SQL, Markdown serialization, or persistence instructions invented by the
  planner.

Structured Outputs should constrain the model, but deterministic local validation remains
authoritative and fails closed.

## Retrieve and write execution remain different

For a future direct retrieval with `entity != null` and `link_scope=null`, exact primary-name/alias
lookup is privileged and returns that entity note when safely resolved. It does not imply a vault-wide
backlink scan.

For writes, a non-null `target.entity` gives Phase 16 a privileged exact primary-name/alias attempt
before semantic/contextual fallback. Failure or ambiguity is not proof of absence. Filters narrow
candidate evidence only; they do not authorize mutation or creation.

Stable note `id` remains the only globally unique semantic identity. Primary names and aliases may
collide. Name/alias collisions are ambiguity evidence, not permission to create `Marta-2` or another
duplicate merely to obtain a free filename.

`entity` is useful creation evidence but is not a universal creation requirement. Occurrence-like
notes such as journal entries or purchases may have sufficient identity through validated type,
domain properties, and context.

## Phase 16 boundary created by this contract

Phase 16 can now focus on safe execution rather than reinterpreting raw user language:

```text
prepared KnowledgeUnit
        |
        v
resolve one existing target when applicable
        |
        +--> RESOLVED -> deterministic property/tag changes + bounded body patch
        |
        +--> AMBIGUOUS -> NEEDS_CLARIFICATION
        |
        `--> UNRESOLVED -> separate creation authorization for record only
```

Phase 16 must still decide/implement:

- exact creation authorization (`UNRESOLVED != CREATE`);
- insufficient-identity/pending behavior;
- deterministic candidate restriction from target filters;
- safe path/ID allocation only after identity/creation authorization;
- path + note loading by resolved stable ID;
- primary-name/alias collision behavior;
- item-level tag application after target resolution;
- minimal type-aware writing guidance for note creation/body formatting;
- bounded semantic body patch contract and stale-revision guard;
- guarded whole-note deletion and inbound-link behavior;
- partial-success/dependency result structure;
- type-change requests;
- reference materialization as ordinary wikilinks.

The preferred body-update direction remains a bounded semantic patch rather than routine whole-note
rewrites:

```text
resolved note + exact current body + intended fact change
        |
        v
semantic patch model
        |
        v
NO_CHANGE | REPLACE | REMOVE | INSERT_AFTER | APPEND
        |
        v
Core validates exact anchors + note ID/revision
        |
        v
Phase 12 persistence
```

Whole-body rewrite is not the normal mutation path.

## Phase 15.2 acceptance focus

Use the existing production `gpt-5.6-sol` / low interpretation boundary. Do not repeat model-selection
experiments. A focused benchmark should prove at least:

1. `Marta es mi hermana` -> `entity=Marta`, mutation separate.
2. `Carrefour Balma cierra a las 20:30` -> `entity=Carrefour Balma`, closing time remains a fact.
3. `Corrige a la amiga de Marta nacida en 1990: ahora vive en Lyon` -> `entity=null`, correct filters,
   Lyon mutation.
4. `la tienda de la esquina` remains contextual (`entity=null`).
5. `¿Qué sé de n8n?` -> direct entity retrieval intent without forcing `type=concept`.
6. `¿Qué sé de Marta?` -> `link_scope=null` direct-note semantics.
7. explicit one-hop related-note query -> correct link scope.
8. graph anchor selected by type/property without a nominal name.
9. independent outer result filters and graph-anchor filters.
10. explicit two-hop intent preserves `max_depth=2` without pretending execution exists.
11. semantic `idea/reflection/...` wording creates no tag filter/mutation.
12. explicit `tag X` retrieval creates `tags contains X` only for a canonical tag.
13. explicit add/remove tag write emits item-level `TagChange` without replacing all tags.
14. Phase 15.1 property/target regression sentinels remain valid.

## Phase 15.3 — generic capability delegation

Phase 15.3 extends the same one-call planner boundary with a third ordered action:

```text
RequestPlan.actions[] = RetrieveAction | WriteAction | DelegateAction
DelegateAction = {kind: "delegate", request: non-empty string, selection: SelectionCriteria | null}
```

The single interpretation call first preserves the richest safe Odyssey candidate set and then chooses
the operation on that set:

```text
request
  |
  +--> candidate set: entity / query / type / filters / link_scope
  `--> operation: retrieve / write / delegate
```

The planner uses retrieval/write for ordinary Odyssey knowledge work. It uses `DelegateAction` only
when fulfilling the request requires a specialized capability such as aggregation/comparison,
external-artifact analysis, or translation. This is semantic operation detection, not keyword routing:
recording an intention to compare is a write, while requesting a comparison is delegated.

`DelegateAction.request` retains the specialized operation and its material constraints. Its optional
`selection` reuses `SelectionCriteria` and must retain safely representable entity, type, filters, and
link scope just as direct retrieval would. Delegation changes what happens to the candidate set; it does
not discard candidate-set structure. `selection=null` remains valid only when the request has no useful,
safely representable Odyssey knowledge set, such as some external-artifact transformations.

No app ID, catalog choice, SQL, execution instruction, fabricated result, or cross-action result binding
is present. Concrete routing, manifests, execution, analytics, ticket parsing, and translation remain
deferred. Mixed independent actions retain their order.

### Accepted optional-type quality limitation

Phase 15.3 acceptance evidence scored 16/18 under the deliberately stricter oracle because A07/A08
omitted the otherwise safe `person` type on a graph anchor while preserving the correct action,
`link_scope`, Marta entity anchor, direction, and depth. This is accepted as a precision limitation,
not a semantic graph failure: `NoteSelector.type` is nullable by contract.

A known type is still useful narrowing evidence. `entity="Marta", type="person"` restricts exact
candidate discovery immediately; `type=null` may inspect exact candidates across canonical types and
therefore expose more ambiguity. Resolution remains fail-closed and never selects an arbitrary
candidate. A type hint also cannot distinguish two different `person` notes with the same exact name,
so it is desirable when safely inferable but not sufficient or required for identity correctness.

## Evidence and related documents

Historical benchmark evidence remains append-only:

- [`benchmarks/phase15_write_planning/`](../../benchmarks/phase15_write_planning/)
- [`benchmarks/phase15_1_schema_write_planning/`](../../benchmarks/phase15_1_schema_write_planning/)
- [`benchmarks/phase15_2_selection_anchors/`](../../benchmarks/phase15_2_selection_anchors/)
- [`benchmarks/phase15_3_capability_delegation/`](../../benchmarks/phase15_3_capability_delegation/)

Schema/ontology and persistence invariants remain canonical in their existing documents/ADRs. The
current phase sequence and state are in [Functional Roadmap](functional-roadmap.md). Cross-phase future
capabilities such as concrete app routing/execution, writer profiles, derived graph/analytics,
observability, and multi-user security are in [Future extension points](future-extension-points.md).
