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

The intended direction is:

```text
user message
    |
    v
single Sol/low interpretation call
    |
    +--> RetrieveAction(s)
    |
    `--> WriteAction / KnowledgeUnit(s)
             |
             +--> subject
             +--> canonical type when safely identified
             +--> intent
             +--> canonical writable properties inferred from the schema
             +--> remaining free-text facts
             `--> references
```

### Phase 15.1 decisions already made

- Canonical properties belong in the write-planning output when the user text expresses them.
  Examples include `person.birth_date`, `person.relationship_to_user`, and
  `journal_entry.entry_date`; future applications may add more properties to the schema without
  requiring a hard-coded planner vocabulary.
- The planner must receive a write-oriented projection of the canonical schema, including writable
  type properties whether or not they are retrieval-filterable. Retrieval capabilities and write
  capabilities are related but are not the same contract.
- `KnowledgeUnit.properties` is an ordered list of generic property changes shaped as
  `{field, op, value}`. Phase 15.1 supports only `set` and whole-property `remove`: `set` carries a
  schema-valid value, while `remove` carries `null`. `record`/`amend` use `set`; `remove` uses
  `remove`; `delete` carries no property changes. The detailed contract is canonical in
  [Phase 15 write planning](phase-15-write-planning.md#phase-151-contract-schema-aware-property-changes).
- Property support is entirely schema-driven. Adding a new canonical type or property that uses an
  already-supported schema `value_type` must require only a schema change, not a planner/prompt/code
  branch naming that type or property. A genuinely new `value_type` requires explicit shared
  validation/Structured-Outputs support and tests; unknown value types fail closed until then.
- Information that maps safely to a canonical property should be represented structurally; knowledge
  that does not map to a property remains in `facts` rather than being forced into metadata.
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
  extraction and `concept` non-fallback behavior while retaining a compact set of Phase 15 regression
  sentinels; there is no reason to repeat model-selection experiments.

### Phase 15.1 examples to validate

- `Marta nació el 3 de mayo de 1990` → `type=person`, `birth_date=1990-05-03`.
- `Marta es mi hermana` → `relationship_to_user` when the canonical property can represent the
  supplied value safely.
- `Corrige: Marta nació en 1991` → an amend operation targeting the structured property rather than
  only adding contradictory prose.
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
- For `record`, first attempt to resolve an existing identity when an identity-bearing subject is
  available. A resolved target means the new knowledge is applied to that target rather than creating
  a duplicate.
- `UNRESOLVED != CREATE` remains an invariant. `UNRESOLVED` means only that the existing-entity
  resolver did not safely identify a target; it is not proof that no matching note exists.
- Creation after an unresolved result therefore requires a separate, explicit creation policy. The
  policy must consider the validated `record` intent, a supported canonical type when required, and
  whether the subject has enough identity to create a meaningful note. A vague phrase such as
  `la tienda de la esquina` must be able to end in `NEEDS_CLARIFICATION` instead of creating a weak
  pseudo-identity.
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
  `NEEDS_CLARIFICATION` for subjects such as `mi mujer`, `la tienda de la esquina`, or other contextual
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
making Phase 16 reinterpret raw user language. Phase 16 then combines prepared-reference resolution,
bounded semantic body mutation, and deterministic persistence because those responsibilities meet at
the point where resolved identities and canonical links become actual note changes. Phase 17 keeps
Core composition and its stable boundary together; Phase 18 then proves that boundary through the
distinct n8n integration responsibility.
