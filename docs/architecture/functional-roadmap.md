# Functional Roadmap

This is Odyssey's canonical intended **functional** phase sequence. It records what the product
should build next, rather than the process roadmap in
[Development Pipeline](development-pipeline.md). Git history and ADRs remain authoritative for
what was actually implemented. The roadmap may change, but a future change must update this file
explicitly rather than relying on agent or chat memory.

Status: ✅ **IMPLEMENTED** · ➡️ **NEXT** · ⬜ **PLANNED** · 💡 **CONDITIONAL / LATER**

## Established sequence

- ✅ **Phase 9 — deterministic exact entity resolution:** exact primary-name and alias evidence.
- ✅ **Phase 10 — semantic entity candidate retrieval:** local ranked candidate evidence only.
- ✅ **Phase 11 — contextual/hybrid existing-entity resolution:** Phase 11A established the
  direction; 11B.1 validated the model/prompt and 11B.2 delivered the production resolver with
  deterministic validation and evidence minimization.
- ✅ **Phase 12 — deterministic entity persistence:** explicit validated create and update
  operations.
- ✅ **Phase 13 — general knowledge context retrieval (`get_context`):** validated-plan retrieval
  over a rebuildable local context index.
- ✅ **Phase 14 — request interpretation / validated `RequestPlan`:** Sol/low turns a message into
  ordered retrieval and content-only create-intent actions without retrieval or persistence.
- ✅ **Phase 15 — write planning / knowledge preparation:** one Sol/low call produces validated
  `RetrieveAction` and semantic `WriteAction` / `KnowledgeUnit` values with target selection,
  intent, facts, and references.
- ✅ **Phase 15.1 — schema-aware write planning:** the same Sol/low interpretation boundary now
  separates target identity evidence from schema-derived property mutations and preserves remaining
  knowledge as free-text facts.

## Current functional phase

➡️ **Phase 15.2 — explicit entity anchors and link-scope planning**

Phase 15.1 is accepted and merged. A final pre-persistence contract review identified two pieces of
semantic information that the single planner call can understand but the current shared selection
shape discards: an explicit nominal entity reference, and an explicit request to navigate wikilink
relationships. Phase 15.2 preserves those signals before Phase 16 so later execution does not have to
reinterpret raw user language.

The detailed design checkpoint is canonical in
[Phase 15.2 — explicit entity and link-scope planning](phase-15-2-selection-anchors.md).

The intended shared selection shape becomes:

```text
SelectionCriteria
├─ entity: str | null
├─ query: str
├─ type: str | null
├─ filters: ContextFilter[]
└─ link_scope: LinkScope | null
```

### Phase 15.2 decisions already made

- `entity` is an unresolved nominal anchor extracted from the user request, not an Odyssey stable ID
  and not proof that the note exists. It may be a primary-name or alias candidate.
- The planner must not turn every mentioned entity into the selected entity. For
  `Corrige a la amiga de Marta nacida en 1990: ahora vive en Lyon`, the write target has
  `entity=null`; Marta is context for identifying another person, not the target.
- Contextual descriptions such as `la tienda de la esquina` do not become nominal identities merely
  because they are noun phrases. When the planner cannot isolate a safe nominal target, `entity=null`
  and the identifying meaning remains in `query`.
- Information represented safely as a mutation remains outside the target query. For
  `Marta es mi hermana`, the target may use `entity=Marta`, `query=Marta`, while
  `relationship_to_user=hermana` remains the property mutation.
- `link_scope=null` is the default and means **do not traverse related notes**. Therefore
  `¿Qué sé de Marta?` means retrieve the Marta entity note, not every note in the vault that mentions
  or links to Marta.
- When the request explicitly asks for linked/related knowledge, `link_scope` preserves the nominal
  anchor, optional anchor type, link direction (`incoming`, `outgoing`, or `both`), and requested
  maximum traversal depth. Phase 15.2 represents that intent but does not execute graph traversal.
- Link traversal refers to Odyssey's ordinary Markdown `[[wikilinks]]`; it does not introduce typed
  edges or a relation ontology.
- `RetrieveAction.plan` and `KnowledgeUnit.target` still share the same selection value but retain
  different execution semantics. For writes, `entity` enables a privileged exact-name/alias attempt
  before semantic fallback. For direct retrieval, `entity` identifies the entity note; a graph
  neighborhood is requested only when `link_scope` is non-null.
- `entity` is useful creation evidence but is not a universal CREATE requirement. Journal entries,
  purchases, and other occurrence-like notes may have sufficient identity from type, domain
  properties, and context without a nominal name.
- Stable note `id` remains globally unique. Primary names and aliases are allowed to collide;
  collisions are ambiguity evidence, not a reason to invent automatic `-2` entities or aliases.
- ADR 0008 remains in force: Phase 15.2 does not restore automatic tag inference or planner tag
  filters. In a query such as `ideas relacionadas con Marta`, `ideas` remains semantic query language
  under the current schema while the explicit relation to Marta can be represented by `link_scope`.
- Use the existing production Sol/low interpretation boundary and a small focused benchmark. Do not
  repeat model-selection experiments.

### Phase 15.2 examples to validate

- `Marta es mi hermana` → write target `entity=Marta`, `query=Marta`; relationship remains the
  property mutation.
- `Carrefour Balma cierra a las 20:30` → `entity=Carrefour Balma`; closing time remains a fact while
  no corresponding canonical property exists.
- `Corrige a la amiga de Marta nacida en 1990: ahora vive en Lyon` → `entity=null`, semantic
  `query=amiga de Marta`, deterministic birth-year filters, and Lyon as the fact mutation.
- `Corrige la tienda de la esquina: cierra a las 20:30` → `entity=null`; the contextual description
  must not be promoted to a nominal identity.
- `¿Qué sé de n8n?` → retrieval `entity=n8n`, `link_scope=null`, and do not force `type=concept`
  merely because the current ontology lacks a software type.
- `¿Qué sé de Marta?` → direct Marta-note semantics with `link_scope=null`.
- `¿Qué notas están directamente relacionadas con Marta?` → explicit one-hop graph scope.
- `¿Qué ideas he tenido relacionadas con Marta?` → incoming one-hop graph scope while `ideas`
  remains semantic query language under the current tag policy.
- An explicit two-hop related-notes request → preserve `max_depth=2` without pretending graph
  traversal is already implemented.

## Next functional phase

⬜ **Phase 16 — resolved knowledge persistence**

After Phase 15.2 is validated, use the existing Phase 11 resolver and Phase 12 persistence primitives
to turn semantic write work into bounded, validated mutations. `save_knowledge` is the likely
coordination boundary, but its exact API is intentionally not frozen yet.

### Phase 16 decisions already made

- **All canonical note types may potentially be created or updated.** Do not add a rigid ontology of
  "stable entity types" versus "occurrence types" unless a demonstrated requirement later demands it.
  A purchase or journal entry can also be corrected; identity behavior should be decided from the
  actual reference/evidence rather than a hard-coded type table.
- For `record`, first attempt to resolve an existing identity when an identity-bearing target is
  available. A resolved target means the new knowledge is applied to that target rather than creating
  a duplicate.
- When Phase 15.2 supplies a non-null target `entity`, Phase 16 should try exact primary-name/alias
  identity first. Failure or ambiguity does not prove absence; the existing semantic/contextual path
  remains the fallback when appropriate.
- Phase 16 must honor validated write `target.filters` by applying them as deterministic candidate
  restrictions before the existing identity decision path. The current Phase 11 resolver does not
  accept arbitrary filters, so add the smallest bridge needed; do not turn `get_context` into the
  identity resolver merely because the selection syntax is shared.
- Write-target filters narrow candidate evidence only. Zero matches are unresolved; multiple matches
  are not bulk-update targets and must still resolve to one safe identity or remain ambiguous.
- `UNRESOLVED != CREATE` remains an invariant. `UNRESOLVED` means only that the existing-entity
  resolver did not safely identify a target; it is not proof that no matching note exists.
- Creation after an unresolved result therefore requires a separate, explicit creation policy. The
  policy must consider the validated `record` intent, a supported canonical type when required, and
  whether the target has enough identity to create a meaningful note. A vague phrase such as
  `la tienda de la esquina` must be able to end in `NEEDS_CLARIFICATION` instead of creating a weak
  pseudo-identity.
- A non-null `entity` is positive creation evidence but not a universal gate. Occurrence-like notes
  can be safely creatable without a nominal entity when their validated type/properties/context provide
  sufficient identity.
- Primary-name or alias collisions must not be treated as permission to create a duplicate. Stable
  IDs are unique; names and aliases may be ambiguous. Path allocation happens only after the identity
  and creation decision is safe.
- `amend`, `remove`, and `delete` require an existing resolved target. Ambiguous or unresolved
  identity must not silently create a new note.
- HITL remains later work, but Phase 16 results should preserve a machine-readable pending state such
  as `NEEDS_CLARIFICATION` so that a later interface can ask the user what was meant instead of
  discarding the original knowledge.
- Structured property mutations should be deterministic once Phase 15.1 has identified the canonical
  field/value operation. Free-form Markdown is a separate problem and should not be treated as if it
  were metadata.
- Partial success is allowed. Independent units that can be persisted safely should not be discarded
  because another independent unit is ambiguous. A unit whose dependency is unresolved remains
  pending together with the knowledge needed to resume it later.
- Internal Odyssey errors or ambiguity explanations must not be written into the user's knowledge
  vault as if they were user facts. Return them as operation status/provenance instead.
- A deterministic `delete_entity` primitive will be needed before whole-note `delete` intent can be
  executed safely.

### Phase 16 preferred direction for safe free-text updates

A full-note LLM rewrite is considered too broad a mutation boundary for routine updates. The preferred
architecture to validate is a bounded semantic patch:

```text
resolved target + current exact note body + intended knowledge change
                         |
                         v
                    semantic LLM
                         |
                         v
          small patch / NO_CHANGE decision
                         |
                         v
                deterministic Core checks
                         |
                         v
                  Phase 12 persistence
```

The LLM should identify only the smallest relevant existing text and proposed replacement/removal or
an insertion point. Core, not the LLM, applies the mutation. A candidate contract may use operations
such as:

```text
NO_CHANGE
REPLACE(old_text, new_text)
REMOVE(old_text)
INSERT_AFTER(anchor_text, new_text)
APPEND(new_text)
```

This direction is preferred over line-number authority. Line numbers change whenever text is inserted
or edited and can point to the wrong content after a concurrent or manual edit. Exact text anchors are
more auditable: Core can require that `old_text` or `anchor_text` occurs exactly once in the exact note
revision supplied to the LLM. Zero or multiple matches must fail closed rather than guessing. The
mutation should also be guarded by the expected note ID and revision/content version so an edit made
between read and write cannot be overwritten silently. Line numbers may still be useful diagnostics,
but should not authorize a mutation by themselves.

The semantic patch LLM must also be able to return `NO_CHANGE` when the intended knowledge is already
present, preventing duplicate prose. Whole-body replacement should not be the normal path; if a future
case genuinely requires broad rewriting, it should be a separately justified and more strongly
validated operation.

### Phase 16 open questions before implementation

- **Creation authorization:** define the exact rule that permits `record + unresolved` to become a
  CREATE without equating failure to resolve with proof of absence.
- **Insufficient identity:** define the deterministic threshold/conditions for returning
  `NEEDS_CLARIFICATION` for targets such as `mi mujer`, `la tienda de la esquina`, or other contextual
  labels that should not automatically become canonical names, while allowing occurrence-like notes
  to use other validated identity evidence.
- **Semantic patch contract:** choose and test the smallest reliable operation vocabulary, exact
  uniqueness checks, revision guard, retry behavior after a stale revision, and whether insertions
  need exact before/after context in addition to an anchor.
- **Existing target access:** `resolve_existing_entity` yields stable identity, while Phase 12 updates
  require path plus expected ID. Add a deterministic way to load `path + Note` from a resolved stable
  ID or enrich the resolution result without weakening boundaries.
- **New ID/path allocation:** define deterministic stable-ID and filename/path generation, including
  collisions and names that are not safe filenames, only after identity/creation authorization has
  succeeded.
- **Name/alias collision behavior:** preserve ambiguity when multiple existing notes share a primary
  name or alias; do not auto-create a distinct entity merely to obtain a free filename.
- **Delete semantics:** implement a guarded `delete_entity` and decide what to do when inbound
  wikilinks reference the note being deleted.
- **Dependency handling:** define the persisted/pending result structure when some units succeed and
  others or their dependencies remain unresolved. Do not invent incomplete links just to force a
  nominal success.
- **Type-change requests:** distinguish a type used only to help resolve the current target from a new
  canonical type the user is explicitly asking to assign. Example: `Odyssey no es un concepto, es un
  proyecto`. A type-change request must not prevent finding the existing note under its old type.
- **No-general-solver guarantee:** accept that some arbitrary natural-language mutations will remain
  ambiguous. The success criterion is safe automation with explicit abstention/pending states, not
  forcing every request into an automatic mutation.

## Remaining intended sequence

⬜ **Phase 17 — executable application flow and stable application boundary**

Compose validated `RequestPlan` actions into a small executable Core application flow: retrieve
context where requested, prepare and save knowledge where approved, and return a stable
application/API result. This is a narrow composition boundary, not a generic workflow engine,
router, DAG, or new service.

Phase 17 is also the natural point to introduce a request-level `trace_id` and a low-invasive tracing
boundary before sustained end-to-end use. Prefer traced adapters/wrappers around LLM and persistence
boundaries plus automatic context propagation (for example `ContextVar`) over manual logging inside
every domain function. Exact trace storage and retention remain an implementation decision for that
phase.

⬜ **Phase 18 — n8n integration and first end-to-end Odyssey use case**

Expose the stable application boundary through n8n orchestration and verify one real, bounded
end-to-end Odyssey use case. n8n remains responsible for external integration and triggers;
`odyssey_core` retains domain behavior. n8n execution identifiers should later participate in the
same end-to-end trace rather than creating an unrelated observability island.

⬜ **Phase 19 — end-to-end hardening**

Harden the proven flow with repeatable integration and failure-path evidence, idempotency and
operational behavior appropriate to the demonstrated use case. Do not broaden the architecture
without evidence.

## Conditional later work

- 💡 **Human-in-the-loop:** add a minimal clarification or approval path when demonstrated ambiguity,
  safety, or user-control needs require it. Phase 16 should preserve pending knowledge so this can be
  added without redesigning persistence.
- 💡 **Derived identity/link graph index:** when graph queries are executable, extend the existing
  rebuildable local SQLite index with the minimum required alias and wikilink/backlink tables instead
  of scanning the complete Markdown vault per request or introducing a new service. Markdown remains
  authoritative and the derived graph must remain rebuildable.
- 💡 **Graph retrieval:** execute validated `link_scope` against that derived graph, with bounded
  traversal and explicit handling of unresolved link targets. Ordinary wikilinks remain untyped by
  default.
- 💡 **Structured analytics and aggregations:** support demonstrated queries such as counts, sums,
  averages, and grouping over derived structured/index data. Do not load the vault into an LLM for
  deterministic arithmetic, and do not force aggregation semantics into `RetrieveAction` before a
  concrete executable contract is designed.
- 💡 **Execution observability:** preserve full request traces across planner, retrieval, resolution,
  persistence, n8n, and LLM boundaries, including model/effort, latency, token counters, estimated
  cost, safe raw/validated outputs, and errors. Keep tracing low-invasive through adapters,
  decorators/context managers, and propagated context; operational logs stay outside the knowledge
  vault and never store credentials/secrets.
- 💡 **Performance and index optimization:** optimize retrieval or indexes only when measurements
  show that current local, rebuildable approaches are inadequate.
- 💡 **Proactive Memory/Context Layer:** consider non-disruptive resurfacing only after the direct
  end-to-end flow proves useful; it remains a later product capability.

Phase 15.2 deliberately preserves semantic information already available in the single planner call
before persistence and graph execution. Phase 16 then uses prepared identity evidence for safe
resolution/creation and bounded mutations without reinterpreting the user request. Phase 17 composes
the application flow and establishes a stable tracing boundary; later derived graph and analytics
capabilities can execute the already-preserved link intent without changing Markdown's source-of-truth
role.
