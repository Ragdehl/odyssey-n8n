# Phase 15.2 — explicit entity and link-scope planning

## Status

Design checkpoint before implementation. Phase 15.1 is accepted and merged. Phase 16 must not start
until this contract gap has been validated and accepted.

## Problem

Phase 15.1 preserves semantic target evidence as `query`, optional canonical `type`, and deterministic
`filters`, but it discards one useful distinction already understood by the planner: whether the user
supplied an explicit nominal reference for the target, such as `Marta`, `Carrefour Balma`, or `n8n`.
Phase 16 would otherwise have to infer again whether a query is a name/alias candidate or a broader
semantic description.

The same planning boundary also cannot currently preserve an explicit request to navigate the
wikilink graph around a named note. This matters for future queries such as "ideas relacionadas con
Marta" without changing the default meaning of "¿Qué sé de Marta?".

The goal is to preserve these two pieces of interpretation in the existing single Sol/low planning
call. Phase 15.2 does **not** implement graph traversal, a new database, aggregation, or persistence.

## Architecture challenge

**PROCEED.** The smallest useful change is to extend the existing shared selection value rather than
add another planner or resolver. No new infrastructure is required for Phase 15.2. The existing
rebuildable SQLite context index already establishes the right future boundary for derived note data;
graph and aggregation execution can extend derived indexing later when implemented.

Important constraints:

- Do not make `entity` a resolved Odyssey ID. It is an unresolved nominal anchor extracted from the
  user request and may be a primary name or alias candidate.
- Do not treat every entity mentioned in a sentence as the selected entity.
- Do not reintroduce automatic tag inference or tag filters. ADR 0008 remains in force; words such as
  `idea`, `reflection`, or `decision` remain semantic query language unless a future canonical schema
  capability explicitly represents the requested restriction.
- Do not add typed-edge ontology. Ordinary Markdown `[[wikilinks]]` remain the relationship source of
  truth.
- `entity` is useful identity evidence, but it is not a universal creation requirement. Occurrence-like
  notes such as journal entries or purchases may have sufficient identity through type, domain
  properties, and context without a nominal name.

## Proposed shared selection contract

`RetrieveAction.plan` and `KnowledgeUnit.target` continue to share the same selection shape:

```text
SelectionCriteria
├─ entity: str | null
├─ query: str
├─ type: str | null
├─ filters: ContextFilter[]
└─ link_scope: LinkScope | null
```

### `entity`

`entity` is the explicit nominal reference for the selected target when the planner can isolate one
safely. It is not a resolved ID and does not assert that the note exists.

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

When no safe nominal target exists, use `entity=null` and retain the identifying meaning in `query`:

```text
"Corrige a la amiga de Marta nacida en 1990: ahora vive en Lyon"
entity = null
query  = "amiga de Marta"
type   = person
filters = birth_date >= 1990-01-01 and birth_date < 1991-01-01
```

`Marta` must **not** become the entity in that example because Marta is mentioned but is not the write
target.

Likewise, descriptions such as `la tienda de la esquina` are not nominal identities merely because
they are noun phrases:

```text
entity = null
query  = "la tienda de la esquina"
```

The planner should fail closed to `null` when unsure.

### Query versus mutation

The Phase 15.1 separation remains unchanged. `query` contains selection meaning, while requested new
knowledge remains in `properties` or `facts`.

For example:

```text
"Marta es mi hermana"

target.entity = "Marta"
target.query  = "Marta"
properties    = relationship_to_user set "hermana"
```

There is no benefit in keeping `es mi hermana` inside the target query once the planner has safely
represented that meaning as the requested mutation.

## `link_scope`

`link_scope` is present only when the request explicitly asks for notes connected through Odyssey's
wikilink graph. Its absence means **do not traverse related notes**.

Proposed shape:

```text
LinkScope
├─ entity: str
├─ type: str | null
├─ direction: incoming | outgoing | both
└─ max_depth: integer >= 1
```

The nested `entity` is the unresolved nominal anchor whose graph neighborhood is requested. Optional
`type` may constrain anchor resolution when the request safely identifies its canonical class. It does
not constrain the result notes; result restrictions remain in the outer `SelectionCriteria`.

`direction` means:

- `incoming`: notes that link to the anchor (backlinks).
- `outgoing`: notes linked from the anchor note.
- `both`: either direction.

`max_depth` preserves how far the user intended graph traversal to go. Execution may initially support
only a smaller bounded depth and must fail explicitly for unsupported depth rather than silently
broadening or narrowing the request.

### Default direct-note semantics

The product default is intentionally narrow:

```text
"¿Qué sé de Marta?"

entity     = "Marta"
query      = "Marta"
type       = person when safely inferred
filters    = []
link_scope = null
```

This means the note representing Marta, not every note in the vault that mentions or links to Marta.
Graph traversal occurs only when the request asks for related/linked knowledge.

### Graph examples

```text
"¿Qué notas están directamente relacionadas con Marta?"

entity     = null
query      = "notas relacionadas con Marta"
link_scope = {
  entity: "Marta",
  type: person,
  direction: both,
  max_depth: 1
}
```

```text
"¿Qué ideas he tenido relacionadas con Marta?"

entity     = null
query      = "ideas que he tenido relacionadas con Marta"
link_scope = {
  entity: "Marta",
  type: person,
  direction: incoming,
  max_depth: 1
}
```

`idea` remains semantic query language under the current schema/ADR 0008. Do not turn it back into a
hard tag filter merely to satisfy this example. If a future application adds an explicit canonical
`idea` type or another deterministic schema field, the existing schema-driven type/filter mechanisms
can then represent that restriction automatically.

A deeper explicit request may preserve a larger `max_depth`, for example two hops, but Phase 15.2 only
proves that the planner can represent the intent. Efficient traversal belongs to later graph-index
execution.

## Retrieve and write execution remain different

The shared shape does not create a shared executor.

For writes, a non-null `entity` gives Phase 16 a privileged exact-name/alias attempt before semantic
fallback. If exact identity is absent or ambiguous, the existing semantic/contextual evidence path and
filters still apply. `entity=null` simply skips that optimization.

For retrieval, a non-null `entity` with `link_scope=null` means direct entity-note retrieval. It does
not imply a vault-wide search for every note mentioning that entity. A non-null `link_scope` requests
an explicit graph neighborhood and will later be executed against derived link data.

## Identity, names, aliases, and creation

Stable note `id` remains the only globally unique semantic identity. Filesystem paths must of course be
physically unique, but primary names and aliases are allowed to collide. Existing exact resolution
already preserves ambiguity rather than pretending names are globally unique.

Phase 16 creation therefore must not treat a filename or alias collision as proof that the new unit is
another entity, nor should it create arbitrary `-2` duplicates simply to obtain a free path. It must
run the approved resolution/creation policy first and preserve ambiguity when identity cannot be
established safely.

A non-null `entity` is strong evidence for nominal identity and can help creation policy, but creation
must not require it universally. For example:

```text
"Hoy estoy pensando si cambiar el sofá"
```

may legitimately plan a `journal_entry` with `entity=null`, `entry_date` set to the current domain
date, and the reflection as a fact. Its creation identity comes from the occurrence semantics, not a
name.

## Future derived graph/index execution

Do not build this in Phase 15.2. When graph retrieval is implemented, prefer extending the existing
rebuildable local SQLite index rather than scanning every Markdown file per query or introducing a new
service.

A future derived shape may include, conceptually:

```text
notes
- id
- path
- primary_name
- type
- revision/source hash

aliases
- note_id
- alias
- normalized_alias

links
- source_id
- target_id nullable until safely resolved
- raw_target

properties
- note_id
- field
- normalized value
- value_type
```

The current context index already stores rebuildable `notes` and normalized `properties`; future
aliases/backlinks/links can extend that derived boundary. Markdown remains the personal-knowledge
source of truth. Deleting the derived knowledge index must remain recoverable by rebuilding it from
canonical notes.

This index also provides a natural performance path for exact identity lookup so direct entity
retrieval does not require reading the complete vault as it grows.

## Future structured analytics and aggregations

Queries such as these are a demonstrated future product need:

```text
"¿Cuántas notas tengo sobre X?"
"¿Cuántas compras hice en Carrefour este año?"
"¿Cuál es el precio medio que he pagado por este producto?"
```

They should eventually execute against derived structured/index data using deterministic operations
such as `COUNT`, `SUM`, `AVG`, and grouping where possible, not by loading the vault into an LLM.

Do **not** force aggregation semantics into the current `RetrieveAction` merely to reserve syntax.
When this work becomes executable, design the smallest explicit aggregate/query action justified by
the real cases. The derived tables remain rebuildable from Markdown; they do not become the knowledge
source of truth.

## Future execution observability

Before sustained real-world use, Odyssey should add end-to-end execution tracing so a single request
can be reconstructed across planner calls, retrieval, resolution, persistence, n8n boundaries, and
LLM calls, including model, effort, latency, token counters, estimated cost, validated/raw outputs,
and failures where safe.

The implementation should be deliberately low-invasive:

```text
request trace context (trace_id)
        |
        +--> traced adapters/wrappers around LLM clients
        +--> traced repository/persistence boundaries
        +--> traced functional/application boundaries
        `--> trace sink
```

Prefer adapters, decorators/context managers, and automatic context propagation (for example Python
`ContextVar`) over manual logging statements inside every domain function. Tests may inject an
in-memory trace sink through fixtures. Operational trace data is separate from the Markdown knowledge
vault and must never contain credentials or secrets. Retention/redaction and the exact SQLite/JSON
storage layout should be decided when the tracing phase is implemented.

## Phase 15.2 acceptance focus

Use the existing production Sol/low interpretation boundary and a small focused benchmark. Do not
repeat model-selection experiments. At minimum prove:

1. `Marta es mi hermana` -> target `entity=Marta`; mutation remains separate.
2. `Carrefour Balma cierra a las 20:30` -> target `entity=Carrefour Balma`; closing time remains a
   fact while no property exists.
3. `Corrige a la amiga de Marta nacida en 1990: ahora vive en Lyon` -> target `entity=null`; Marta is
   not mistaken for the target; birth-year filters and Lyon fact remain correct.
4. `Corrige la tienda de la esquina: cierra a las 20:30` -> `entity=null`; contextual descriptions do
   not become nominal identities.
5. `¿Qué sé de n8n?` -> retrieval `entity=n8n`, `link_scope=null`; do not force `type=concept` merely
   because n8n lacks a current canonical software type.
6. `¿Qué sé de Marta?` -> direct entity-note semantics, `link_scope=null`.
7. `¿Qué notas están directamente relacionadas con Marta?` -> explicit one-hop link scope.
8. `¿Qué ideas he tenido relacionadas con Marta?` -> incoming one-hop link scope while `ideas`
   remains semantic query language under the current tag policy.
9. A suitable explicit two-hop query -> preserves `max_depth=2` without pretending traversal is
   already implemented.
10. Existing Phase 15.1 property/target regression sentinels remain valid.

Phase 15.2 still does not resolve repository identity, execute graph queries, choose CREATE versus
UPDATE, allocate IDs/paths, mutate Markdown, persist data, or run aggregations.
