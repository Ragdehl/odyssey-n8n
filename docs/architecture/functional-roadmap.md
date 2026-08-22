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
  `RetrieveAction` and semantic `WriteAction` / `KnowledgeUnit` values with subject, optional type,
  intent, facts, and references. The Phase 15 benchmark and targeted follow-up are complete.

## Current functional phase

➡️ **Phase 15.1 — schema-aware write planning**

Phase 15 remains accepted for the contract it validated, but a pre-persistence gap was found after
merge: `KnowledgeUnit` currently carries free-text facts but not the canonical writable properties
that are defined by note type in `config/note-schema.json`. Persistence cannot safely reconstruct
those properties later without reinterpreting the request. Phase 15.1 therefore extends the same
single Sol/low interpretation boundary rather than introducing a second interpretation pass.

Contract review also identified two simplifications for write-target identity and classification: do
not create a second write-only selection language, and do not overload the target's current type with
a requested resulting type. Reuse the same `query` / `type` / `filters` shape already used by
`RetrieveAction.plan`, while representing an explicit type reassignment separately as `new_type`.

The intended direction is:

```text
user message
    |
    v
single Sol/low interpretation call
    |
    +--> RetrieveAction
    |       `--> plan(query, type, filters)
    |
    `--> WriteAction / KnowledgeUnit(s)
             |
             +--> target(query, type, filters)
             +--> intent
             +--> new_type when canonical type should change
             +--> canonical writable property changes inferred from the schema
             +--> remaining free-text facts
             `--> references
```

### Phase 15.1 decisions already made

- `RetrieveAction.plan` and `KnowledgeUnit.target` share one closed selection shape:
  `query`, optional canonical current `type`, and deterministic `filters`. They should reuse the same
  dynamic filter vocabulary, Structured Outputs construction, operator/value rules,
  type-compatibility checks, and deterministic filter validation.
- Sharing the selection contract does **not** make write-target selection a `RetrieveAction` and does
  not imply a common executor. Retrieval may return zero-to-many notes for the user; a write target
  must later resolve safely to one existing identity or abstain, with `record` creation handled by a
  separate policy.
- Phase 15.1 intentionally refines the Phase 15 write-unit shape from top-level `subject`/`type` to a
  nested `target(query, type, filters)` plus nullable `new_type`. Historical Phase 15 benchmark
  evidence remains unchanged.
- `target.query` remains non-empty and carries identity meaning that is not safely expressible as
  deterministic filters. When the request supplies a stable name, preserve it in the query even if
  filters also exist.
- A property mentioned only to identify the target belongs in `target.filters` when it maps safely to
  the canonical filter contract; it is **not** a property mutation. Non-filterable identity wording
  remains in `target.query`.
- The same property may appear on both sides when the user identifies an old value and explicitly
  supplies a corrected new value: the old value can constrain `target.filters`, while the new value is
  a `properties` mutation.
- `target.type` means the current type used only as selection evidence. `new_type` means the desired
  resulting canonical type when the user is asserting or correcting classification. The desired new
  type must not be used as a hard current-type filter unless the request independently establishes
  that current type.
- `new_type` may be used with `record` or `amend`; `remove` and `delete` require it to be null. A type
  change counts as mutation payload even when `properties` and `facts` are empty.
- When `new_type` is non-null, explicit property mutations are validated against the destination
  `new_type`; otherwise they are validated against `target.type`.
- Canonical properties belong in the mutation output when the user text expresses them as knowledge
  to record/change/remove. Examples include `person.birth_date`, `person.relationship_to_user`, and
  `journal_entry.entry_date`; future applications may add more properties to the schema without
  requiring a hard-coded planner vocabulary.
- The planner must receive a write-oriented projection of the canonical schema, including writable
  type properties whether or not they are retrieval-filterable. Retrieval/selection capabilities and
  write capabilities are different views of the same canonical schema, not separate registries.
- `KnowledgeUnit.properties` is an ordered list of generic property changes shaped as
  `{field, op, value}`. Phase 15.1 supports only `set` and whole-property `remove`: `set` carries a
  schema-valid value, while `remove` carries `null`. `record`/`amend` use `set`; `remove` uses
  `remove`; `delete` carries no property changes. The detailed contract is canonical in
  [Phase 15 write planning](phase-15-write-planning.md#phase-151-contract-schema-aware-write-targets-type-changes-and-property-changes).
- Property support is entirely schema-driven. Adding a new canonical type or property whose
  `value_type` and constraint/format semantics are already supported by Core must require only a
  schema change, not a planner/prompt/code branch naming that type or property. If that property is
  `filterable`, it must also flow into both retrieval filters and write-target filters automatically.
  A genuinely new value type or validation/constraint primitive requires explicit shared support and
  tests; unsupported semantics fail closed until then.
- Compatible declarations of the same filterable property ID under multiple note types must merge
  their `applies_to` type sets. Incompatible definitions must fail closed instead of silently letting
  one type overwrite another in planner capabilities.
- Information that maps safely to a canonical property mutation should be represented structurally;
  knowledge that does not map to a property remains in `facts` rather than being forced into metadata.
- `references` remain in-plan logical links between `KnowledgeUnit` values. Phase 16 later resolves or
  creates referenced units and materializes actual Markdown links from their stable identities/paths.
- `concept` is not a fallback for unknown classification. Its intended meaning is a reusable,
  identifiable abstract subject or topic with its own semantic identity. If no canonical type is
  safely supported, `type=null` is preferable to inventing `concept`.
- Tags remain deferred. They still exist in the schema, but Phase 15.1 will not add automatic tag
  inference or make tags properties of `concept`. `type` answers what kind of thing the note is;
  tags may later describe a cross-cutting character such as idea/reflection/decision if that proves
  useful.
- The existing Phase 15 safety boundaries remain: the planner does not resolve repository identity,
  choose physical CREATE versus UPDATE, allocate IDs or paths, rewrite Markdown, or persist data.
- A new Sol/low benchmark is required for the extended contract. It should focus on property
  extraction, target selection versus mutation, explicit type reassignment and destination-property
  scoping, dynamic schema behavior, and `concept` non-fallback behavior while retaining a compact set
  of Phase 15 regression sentinels; there is no reason to repeat model-selection experiments.

### Phase 15.1 examples to validate

- `Marta nació el 3 de mayo de 1990` → write target `query=Marta`, `type=person`, no target filter
  required, `new_type=null`, and mutation `birth_date=1990-05-03`.
- `Marta es mi hermana` → mutation `relationship_to_user=hermana` when the canonical property can
  represent the supplied value safely.
- `Corrige la relación de la persona que nació el 3 de mayo de 1990: es mi hermana` → target
  `type=person`, `birth_date eq 1990-05-03` as selection evidence, and only
  `relationship_to_user=hermana` as the mutation.
- `Corrige la persona nacida el 3 de mayo: nació el 4 de mayo` → old birth date may be target-selection
  evidence while the new birth date is the property mutation; do not collapse the two roles.
- `Corrige a la amiga de Marta nacida en 1990` → semantic relationship wording remains in
  `target.query`, while the year may use deterministic `birth_date` filters.
- `Odyssey no es un concepto, es un proyecto` → target may use current `type=concept`, while
  `new_type=project`; do not search only for a project and miss the existing concept note.
- `Odyssey es un proyecto` → when the request asserts the desired classification but not the current
  stored type, prefer `target.type=null` plus `new_type=project`.
- A synthetic type-change case with destination properties must verify that `properties` are scoped to
  the new type, including required destination properties when the request supplies them.
- `Quita la fecha de nacimiento de Marta` → removal of the structured property.
- `Escribí una entrada de diario sobre el viaje del día 20` → `journal_entry.entry_date` when the
  request identifies that domain date.
- `Entity resolution es el proceso de decidir qué entidad existente corresponde a una referencia`
  → may be `concept` because the subject is a reusable identifiable abstraction.
- `Hoy estoy pensando si cambiar el sofá` → must not become `concept` merely because no more specific
  type fits.
- `Carrefour Balma cierra a las 20:30` → remains a free-text fact unless the schema defines a
  corresponding property; the planner must not invent one.

## Next functional phase

⬜ **Phase 16 — resolved knowledge persistence**

After Phase 15.1 is validated, use the existing Phase 11 resolver and Phase 12 persistence primitives
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
- `amend`, `remove`, and `delete` require an existing resolved target. Ambiguous or unresolved
  identity must not silently create a new note.
- A validated `new_type` is a requested resulting classification, never identity evidence by itself.
  If a `record` target remains unresolved and later creation is independently authorized, `new_type`
  may supply the resulting creation type.
- When a resolved note actually changes canonical type, Phase 16 must rebuild its type-specific
  property set for the destination schema instead of leaving incompatible old properties behind.
  Because Phase 15.1 does not have the stored note, this reconstruction happens after resolution via a
  bounded schema-rematerialization LLM step: current relevant note metadata/body + validated change
  intent + destination type definition in, complete destination property proposal or abstention out.
  Core removes old type-specific properties, sets the new type, validates the complete proposed
  destination properties, and refuses/defer the update if required properties cannot be justified.
  This is a special bounded type-change path, not a generic old-type/new-type mapping table or a free
  rewrite of lifecycle metadata/body.
- If a resolved note already has `new_type`, there is no reclassification migration; ordinary
  structured property mutation rules apply.
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
  labels that should not automatically become canonical names.
- **Semantic patch contract:** choose and test the smallest reliable operation vocabulary, exact
  uniqueness checks, revision guard, retry behavior after a stale revision, and whether insertions
  need exact before/after context in addition to an anchor.
- **Existing target access:** `resolve_existing_entity` yields stable identity, while Phase 12 updates
  require path plus expected ID. Add a deterministic way to load `path + Note` from a resolved stable
  ID or enrich the resolution result without weakening boundaries.
- **New ID/path allocation:** define deterministic stable-ID and filename/path generation, including
  collisions and names that are not safe filenames, before calling `create_entity`.
- **Delete semantics:** implement a guarded `delete_entity` and decide what to do when inbound
  wikilinks reference the note being deleted.
- **Dependency handling:** define the persisted/pending result structure when some units succeed and
  others or their dependencies remain unresolved. Do not invent incomplete links just to force a
  nominal success.
- **No-general-solver guarantee:** accept that some arbitrary natural-language mutations will remain
  ambiguous. The success criterion is safe automation with explicit abstention/pending states, not
  forcing every request into an automatic mutation.

## Remaining intended sequence

⬜ **Phase 17 — executable application flow and stable application boundary**

Compose validated `RequestPlan` actions into a small executable Core application flow: retrieve
context where requested, prepare and save knowledge where approved, and return a stable
application/API result. This is a narrow composition boundary, not a generic workflow engine,
router, DAG, or new service.

⬜ **Phase 18 — n8n integration and first end-to-end Odyssey use case**

Expose the stable application boundary through n8n orchestration and verify one real, bounded
end-to-end Odyssey use case. n8n remains responsible for external integration, triggers, retries,
and observability; `odyssey_core` retains domain behavior.

⬜ **Phase 19 — end-to-end hardening**

Harden the proven flow with repeatable integration and failure-path evidence, idempotency and
operational behavior appropriate to the demonstrated use case. Do not broaden the architecture
without evidence.

## Conditional later work

- 💡 **Human-in-the-loop:** add a minimal clarification or approval path when demonstrated ambiguity,
  safety, or user-control needs require it. Phase 16 should preserve pending knowledge so this can be
  added without redesigning persistence.
- 💡 **Performance and index optimization:** optimize retrieval or indexes only when measurements
  show that current local, rebuildable approaches are inadequate.
- 💡 **Proactive Memory/Context Layer:** consider non-disruptive resurfacing only after the direct
  end-to-end flow proves useful; it remains a later product capability.

Phase 15.1 deliberately repairs the write-planning representation before persistence rather than
making Phase 16 reinterpret raw user language. Phase 16 then combines prepared-target resolution,
bounded type-property rematerialization when classification changes, bounded semantic body mutation,
reference materialization, and deterministic persistence because those responsibilities meet at the
point where resolved identities and canonical links become actual note changes. Phase 17 keeps Core
composition and its stable boundary together; Phase 18 then proves that boundary through the distinct
n8n integration responsibility.