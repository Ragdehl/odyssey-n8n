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
  one revision-guarded Phase 12 update.
- ✅ **Phase 16.5 — pre-writer reference binding:** 16.5A preserves deterministic planner occurrence
  markers and human-readable mentions; 16.5B preflights each target once and resolves or preallocates
  referenced identities; 16.5C deterministically renders only safely bound `[[path|mention]]` links
  before Luna. Ambiguous/unresolved references remain readable plain mentions plus explicit pending
  reference results. Focused Luna-medium linked-writer evidence is reproducible at 6/6 PASS.
- ➡️ **Phase 16.6 — CREATE materialization:** consume the already-preallocated CREATE identity/path,
  stage canonical metadata deterministically, generate a complete body through the selected
  Luna/medium policy only when free-text facts exist, validate bound links/schema, and persist once.
- ⬜ **Phase 16.7 — remaining Phase 16 mutation semantics:** guarded soft delete/inbound-link policy,
  explicit bulk cardinality, dependency/partial-success results, and type-change handling before
  general RequestPlan orchestration.

The canonical Phase 15 / 15.1 / 15.2 / 15.3 planner contract is centralized in
[Phase 15 planning contract](phase-15-write-planning.md). The selected write policy and historical
benchmark evidence are centralized in [Phase 16 writing checkpoint](phase-16-writing.md). The
pre-writer reference-binding order, mention/alias boundary, and pending-reference direction are
centralized in [Phase 16 reference binding](phase-16-reference-binding.md). The active CREATE
materialization contract is centralized in
[Phase 16.6 CREATE materialization](phase-16-create-materialization.md).

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

✅ **Phase 16.5 — reference binding before body writing** is complete. Phase 16.5A freezes
`KnowledgeReference(target_index, role, mention)` plus `{{ref:N}}` markers local to each unit's
`references` array, so placement is preserved before Luna sees the facts. Phase 16.5B owns target
resolution and identity/path preallocation. Phase 16.5C consumes those results and replaces only
safely bound marker occurrences with `[[vault/path-without-.md|mention]]`. It does not resolve
identity, persist pending artifacts, run HITL, or decide whether mentions should become aliases. See
[Phase 16 reference binding](phase-16-reference-binding.md).

The established pre-writer order is:

```text
1. preserve reference occurrence in planner facts
        |
2. resolve existing reference targets / authorize same-request CREATE targets
        |
3. allocate stable identity + path for authorized CREATEs (no persistence yet)
        |
4. Core materializes only safe [[path|mention]] links
        |
5. Luna receives already-linked facts for CREATE/UPDATE
        |
6. validate complete staged notes and persist through bounded Phase 16 semantics
```

If a reference target remains ambiguous among several notes, Phase 16.5C does **not** guess one of
them. The occurrence stays as its human-readable `mention`, and the unresolved reference is returned
as pending work together with candidate stable IDs when known. No second LLM rediscovers link
placement after writer output.

The preferred later HITL direction is more navigable than silently leaving that ambiguity forever:
once Odyssey has a durable pending-work boundary, it may create a small internal Markdown artifact
that links the real candidates and let the source occurrence temporarily point to that artifact, for
example `[[pending/Marta-ambiguity-<uuid>|Una Marta]]`. Once the identity is resolved, the source link
should normally be replaced with the real target and the temporary artifact archived or removed.
This is workflow state, not automatically a new canonical note type, and is outside Phase 16.5C.

A reference also does **not** authorize an automatic inverse mutation in the referenced note. Store the
user-supplied relationship once and rely first on ordinary semantic context retrieval for reverse
natural-language questions; the context projection already renders wikilinks as readable entity text.
Explicit graph/backlink traversal remains separate and evidence-driven.

➡️ **Phase 16.6 — CREATE materialization** now follows that completed preflight/binding boundary. The
canonical contract is [Phase 16.6 CREATE materialization](phase-16-create-materialization.md).
`save_knowledge` remains a likely later coordination boundary, but its exact API should be decided from
implementation evidence rather than frozen prematurely.

The Phase 16.6 slice is deliberately per-note:

```text
CREATE-authorized KnowledgeUnit + matching preflight
        |
        +--> deterministic canonical metadata
        |       `--> invalid/incomplete -> fail before paid writer
        |
        +--> no free-text facts -> empty body / no writer
        |
        `--> rendered free-text facts -> Luna / medium -> exactly one CREATE_BODY
                                               |
                                               v
                                  Core body/link/schema validation
                                               |
                                               v
                                       create_entity() once
```

The existing generic writer policy remains the simplest starting point. Phase 16.3 already exercised
15 CREATE_BODY cases across several note semantics, so Phase 16.6 does not add a type-writing-profile
system unless focused evidence demonstrates a concrete failure that requires one.

Phase 16 materialization must still cover after 16.6:

- guarded whole-note delete behavior and inbound-link policy;
- explicit bulk cardinality;
- dependency/partial-success results across several units;
- type-change requests.

Existing notes remain changed through bounded operations (`NO_CHANGE`, `REPLACE`, `REMOVE`,
`INSERT_AFTER`, `APPEND`) validated and applied by Core, not routine whole-note LLM rewriting.
CREATE free text uses exactly one validated `CREATE_BODY`, never an UPDATE operation family.

Because 16.6 materially extends the production writer contract to CREATE and CREATE facts may now
contain canonical wikilinks, focused live regression evidence with the already-selected
`gpt-5.6-luna` / medium writer is required. Keep it proportional: approximately six representative
CREATE calls, not a new model-selection benchmark. Deterministic failure/schema tests remain required
and do not replace live semantic evidence.

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

- 💡 **Human-in-the-loop / durable pending references:** minimal clarification/approval path when
  ambiguity or user control requires it. Ambiguous reference binding is a concrete first use case.
  Prefer an inspectable internal Markdown pending artifact that links known candidate notes and can be
  referenced temporarily from the source occurrence. After resolution, replace the source link with
  the real note and archive/remove the temporary artifact. Keep this workflow state outside the
  canonical user-knowledge ontology unless later evidence justifies a dedicated type.
- 💡 **Mention-to-alias promotion:** some occurrence wording such as `Carrefour` or `la amiga de
  Laura` may be useful reusable identity vocabulary, while transient phrases such as `la chica con la
  que cenamos ayer` should not become durable aliases. Keep Phase 16.5C deterministic; introduce alias
  promotion only through a separate explicit semantic contract with evidence.
- 💡 **Derived identity/link graph index:** extend the rebuildable SQLite index with aliases and
  wikilinks/backlinks when graph execution is needed; Markdown remains authoritative.
- 💡 **Graph retrieval:** keep ordinary semantic relationship questions semantic-first because
  `ContextIndex` humanizes wikilinks before embedding. Use bounded graph/backlink traversal for
  explicit structural/neighborhood questions, or later as a recall supplement only if benchmarks show
  semantic retrieval misses inverse relationships.
- 💡 **Structured analytics / aggregations:** deterministic counts, sums, averages and grouping over
  rebuildable structured/index data rather than loading the vault into an LLM.
- 💡 **App/capability delegation:** let the top-level planner distinguish direct Core knowledge work
  from generic delegated capabilities; route delegated actions later with a cheap/local router over
  compact app manifests and load only the selected app contract. Purchase/ticket processing, project
  workflows, and translation-related workflows are expected future application families on this
  shared knowledge foundation rather than reasons to expand the top-level planner indefinitely.
- 💡 **Type-aware writing profiles:** Phase 16.6 intentionally starts with the already-tested generic
  CREATE writer contract; add schema-linked per-type guidance later only if measured body-quality
  failures demonstrate a concrete need.
- 💡 **Tag vocabulary evolution:** keep Phase 15.2 explicit-only with the current controlled registry;
  decide later whether values such as `idea` become types and whether user-extensible transversal tags
  are needed.
- 💡 **Large-vault retrieval reduction:** keep MiniLM as broad high-recall retrieval and benchmark a
  recall-first Luna selector over Top-100 candidates before reducing the strong resolver context; do
  not treat the Phase 16 writer evidence as proof that this retrieval path is safe. Detailed acceptance
  evidence and long-note coverage live in [Future extension points](future-extension-points.md).
- 💡 **Execution observability:** preserve reconstructable planner/retrieval/resolution/persistence/n8n/
  LLM traces including safe model/usage/cost/error metadata, with redaction and retention controls.
- 💡 **Multi-user ownership/sharing:** design authentication, authorization and storage boundaries
  before adding note-level ownership/grant metadata.
- 💡 **Performance/index optimization:** optimize only from measurements.
- 💡 **Proactive Memory/Context Layer:** non-disruptive resurfacing only after the direct end-to-end flow
  proves useful.

Git history, ADRs, benchmark records, branches, PRs, and CI remain authoritative for what actually
happened. This roadmap intentionally avoids duplicating those records.