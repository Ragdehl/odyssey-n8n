# Functional Roadmap

This is Odyssey's canonical intended **functional phase sequence**. It answers what is implemented,
what is current, and what comes next. Detailed contracts live in their dedicated architecture
documents and are linked here rather than duplicated.

Status: ✅ **IMPLEMENTED** · ➡️ **NEXT** · ⬜ **PLANNED** · 💡 **CONDITIONAL / LATER**

## Established sequence

- ✅ **Phase 9 — deterministic exact entity resolution:** exact primary-name and alias evidence.
- ✅ **Phase 10 — semantic entity candidate retrieval:** local ranked candidate evidence only.
- ✅ **Phase 11 — contextual/hybrid existing-entity resolution:** deterministic validation plus one
  bounded contextual decision path.
- ✅ **Phase 12 — deterministic entity persistence:** explicit validated create/update primitives.
- ✅ **Phase 13 — general knowledge context retrieval (`get_context`):** validated-plan retrieval over
  a rebuildable local context index.
- ✅ **Phase 14 — request interpretation / validated `RequestPlan`:** Sol/low converts user language
  into ordered retrieval-oriented actions without executing them.
- ✅ **Phase 15 — write planning / knowledge preparation:** adds semantic write actions and logical
  knowledge units beside retrieval actions.
- ✅ **Phase 15.1 — schema-aware write planning:** adds shared target selection plus schema-derived
  property mutations and validates the refined contract with Sol/low.
- ✅ **Phase 16.1 — safe write-target resolution / create-update decision:** composes one validated
  `KnowledgeUnit` with the existing resolver into non-persisting UPDATE, CREATE, or clarification.
- ✅ **Phase 16.2 / 16.3 — write-path evidence and bounded-writer selection:** local MiniLM/NLI
  semantic gates were rejected for the write path; measured evidence selects one full-note
  `gpt-5.6-luna` / medium bounded writer policy for free-text CREATE/UPDATE, with deterministic
  structure and exact normalized duplicate shortcuts remaining in Core.
- ✅ **Phase 16.4 — existing-note UPDATE materialization:** one already-resolved UPDATE now stages
  deterministic properties/tags, validates Luna-medium full-note bounded operations, and performs
  one revision-guarded Phase 12 update. CREATE remains deliberately unimplemented.

The canonical Phase 15 / 15.1 / 15.2 / 15.3 planner contract is centralized in
[Phase 15 planning contract](phase-15-write-planning.md). The selected write policy and historical
benchmark evidence are centralized in [Phase 16 writing checkpoint](phase-16-writing.md).

## Completed Phase 15 refinements

✅ **Phase 15.2 — explicit identity, link-scope, and explicit-tag planning**

Phase 15.2 is a final pre-persistence refinement of the same single Sol/low interpretation boundary.
It preserves information that later execution should not have to infer again:

- an explicit unresolved nominal `entity` anchor when safely present;
- explicit wikilink-neighborhood intent through a generalized, non-recursive graph anchor selector;
- direct-note semantics by default (`¿Qué sé de Marta?` does not imply backlink traversal);
- explicit-only controlled tag filters and item-level tag changes, while semantic wording alone never
  creates a tag restriction or mutation.

Implementation must remain schema-driven and fail closed. Phase 15.2 does **not** resolve identities,
traverse the graph, persist notes, create new tags, route apps, or run aggregations.

### Acceptance

Use the existing production `gpt-5.6-sol` / low planner boundary and a small focused benchmark. Do not
repeat model-selection experiments. The benchmark should cover nominal versus contextual targets,
graph anchors by name and by properties, independent result/anchor filters, direct-note semantics,
explicit depth, explicit-only tag reads/writes, and Phase 15.1 regression sentinels.

✅ **Phase 15.3 — generic capability delegation**

Phase 15.3 completes the planning boundary with a generic `DelegateAction` for work that ordinary
Odyssey retrieval/write semantics cannot satisfy. The same Sol/low call distinguishes direct knowledge
work from aggregation, external-artifact analysis, translation, or another specialized capability.
It preserves an optional existing `SelectionCriteria`, but never selects an app, exposes an app
catalog, routes, executes, or binds a delegated result to a later action.

## Next functional phase

➡️ **Phase 16 — resolved knowledge materialization**

✅ **Phase 16.1 — safe target decision** is complete. It composes a validated single
`KnowledgeUnit` with Phase 9–11 resolution and returns only `UPDATE`, `CREATE`, or
`NEEDS_CLARIFICATION`; it allocates no ID/path and persists nothing. Creation is generic only for
an unresolved `record` with a validated canonical type, including an unnamed contextual entity.
No type, ambiguity, or unresolved amend/remove/delete requires clarification. Deterministic target
filters narrow authoritative candidate IDs; they never become similarity evidence.

✅ **Phase 16.2 / 16.3 — write-policy evidence** is also complete. The initial materialization
implementation should not add a semantic routing ladder. Its selected free-text path is:

```text
resolved KnowledgeUnit
        |
        +--> deterministic properties / explicit tags
        |
        +--> exact normalized duplicate -> NO_CHANGE
        |
        `--> full authoritative note -> Luna / medium -> bounded operations
                                            |
                                            v
                            Core exact-span / revision / schema validation
                                            |
                                            v
                                     persist once
```

MiniLM/NLI writer filtering, Luna-low/easy-case routing, and Terra/Sol writer fallback are not part of
the selected initial implementation. MiniLM remains available for separate broad-retrieval use cases
where recall evidence supports it.

✅ **Phase 16.4 — existing-note UPDATE materialization** is complete. It accepts only a resolved
UPDATE target, stages deterministic properties/tags, calls the selected full-note Luna-medium writer
only for non-duplicate free text, validates exact bounded operations, and calls Phase 12
`update_entity()` once with an expected revision. No orchestration boundary is introduced.

The next Phase 16 work starts with CREATE materialization; `save_knowledge` remains a likely later
coordination boundary, but its exact API should be decided from implementation evidence rather than
frozen prematurely.

Phase 16 materialization must still cover:

- privileged exact name/alias resolution when `target.entity` is present, with semantic/contextual
  fallback when appropriate;
- deterministic target-filter candidate restriction without turning `get_context` into the identity
  resolver;
- `UNRESOLVED != CREATE` and the existing explicit `record` creation-authorization policy;
- safe handling of insufficient identity and machine-readable `NEEDS_CLARIFICATION`;
- primary-name/alias ambiguity without inventing duplicate `-2` entities;
- stable ID/path allocation only after identity/creation authorization;
- deterministic schema property and explicit tag changes after target resolution;
- minimal type-aware note-writing guidance where demonstrated before body rendering is finalized;
- selected Luna/medium bounded free-text writing with full authoritative existing-note context;
- Core validation of exact spans, schema and current revision before applying writer output;
- one atomic persistence operation after the complete write plan validates;
- guarded whole-note delete behavior and inbound-link policy;
- reference materialization as ordinary Markdown `[[wikilinks]]`;
- explicit bulk cardinality, partial-success/dependency results and type-change requests.

Existing notes must be changed through bounded operations (`NO_CHANGE`, `REPLACE`, `REMOVE`,
`INSERT_AFTER`, `APPEND`) validated and applied by Core, not routine whole-note LLM rewriting.

## Remaining intended sequence

⬜ **Phase 17 — executable application flow and stable application boundary**

Compose validated `RequestPlan` actions into a small Core application flow and return a stable
application/API result. This is a composition boundary, not a generic workflow engine.

Phase 17 is also the natural point to introduce low-invasive request tracing: one propagated
`trace_id`, traced adapters/wrappers around LLM and persistence boundaries, and a separate operational
trace sink rather than manual logging in every domain function.

⬜ **Phase 18 — n8n integration and first end-to-end Odyssey use case**

Expose the stable application boundary through n8n and prove one real bounded end-to-end use case.
n8n remains responsible for external integration/triggers; domain behavior remains in `odyssey_core`.
Operational n8n execution identifiers should participate in the same end-to-end trace rather than
forming an unrelated observability island.

⬜ **Phase 19 — end-to-end hardening**

Harden the proven flow with repeatable integration/failure-path evidence, idempotency, operational
behavior, and measured performance. Do not broaden the architecture without evidence.

## Conditional later work

The detailed cross-phase direction is centralized in
[Future extension points](future-extension-points.md). In short:

- 💡 **Human-in-the-loop:** minimal clarification/approval path when ambiguity or user control requires
  it; Phase 16 should preserve pending work so this can be added later.
- 💡 **Derived identity/link graph index:** extend the rebuildable SQLite index with aliases and
  wikilinks/backlinks when graph execution is needed; Markdown remains authoritative.
- 💡 **Graph retrieval:** execute validated `link_scope` with bounded traversal and explicit unresolved
  link handling.
- 💡 **Structured analytics / aggregations:** deterministic counts, sums, averages and grouping over
  rebuildable structured/index data rather than loading the vault into an LLM.
- 💡 **App/capability delegation:** let the top-level planner distinguish direct Core knowledge work
  from generic delegated capabilities; route delegated actions later with a cheap/local router over
  compact app manifests and load only the selected app contract.
- 💡 **Tag vocabulary evolution:** keep Phase 15.2 explicit-only with the current controlled registry;
  decide later whether values such as `idea` become types and whether user-extensible transversal tags
  are needed.
- 💡 **Execution observability:** preserve reconstructable planner/retrieval/resolution/persistence/n8n/
  LLM traces including safe model/usage/cost/error metadata, with redaction and retention controls.
- 💡 **Multi-user ownership/sharing:** design authentication, authorization and storage boundaries
  before adding note-level ownership/grant metadata.
- 💡 **Performance/index optimization:** optimize only from measurements.
- 💡 **Proactive Memory/Context Layer:** non-disruptive resurfacing only after the direct end-to-end flow
  proves useful.

Git history, ADRs, benchmark records, branches, PRs, and CI remain authoritative for what actually
happened. This roadmap intentionally avoids duplicating those records.
