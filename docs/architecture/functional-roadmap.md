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
- ✅ **Phase 15 — write planning / knowledge preparation:** semantic write actions and logical
  knowledge units beside retrieval actions.
- ✅ **Phase 15.1 — schema-aware write planning:** shared target selection plus schema-derived
  property mutations.
- ✅ **Phase 15.2 — explicit identity, link-scope, and explicit-tag planning.**
- ✅ **Phase 15.3 — generic capability delegation:** planning can preserve delegated work without
  routing or executing it.
- ✅ **Phase 16.1 — safe write-target resolution / create-update decision.**
- ✅ **Phase 16.2 / 16.3 — write-path evidence and bounded-writer selection:** existing-note semantic
  body reconciliation uses the evidenced `gpt-5.6-luna` / medium boundary when required.
- ✅ **Phase 16.4 — existing-note UPDATE materialization.**
- ✅ **Phase 16.5 — pre-writer reference binding:** target preflight, stable identity/path allocation,
  safe wikilink binding, and explicit unresolved-reference evidence.
- ✅ **Phase 16.6 — deterministic CREATE materialization:** no generic CREATE LLM call.
- ✅ **Phase 16.7A — explicit cardinality + deterministic bulk UPDATE:** `one | all_matching`, with
  semantic similarity excluded from bulk mutation authority.
- ✅ **Phase 16.7B — soft DELETE:** recoverable `deleted: true`, excluded from ordinary active
  retrieval/resolution/bulk behavior.
- ✅ **Phase 16.7C — type migration:** one active note can change canonical type in place while
  preserving stable ID/path and failing closed on information loss or missing required destination data.
- ✅ **Phase 17A — executable Core application flow + stable `request_id`:** one logical request composes
  retrieval, bounded writes, dependencies, bulk behavior, and typed deferred evidence.
- ✅ **Phase 17B — durable pending work:** actionable incomplete post-plan work survives process exit
  outside canonical knowledge, keyed by the same `request_id`.
- ✅ **Phase 17C — local Git history per logical request:** successful Markdown mutations can be audited
  and recovered through request-correlated local Git commits without making Git the source of truth.

Canonical detail for these completed phases lives in:

- [Phase 15 planning contract](phase-15-write-planning.md)
- [Phase 16 writing checkpoint](phase-16-writing.md)
- [Phase 16 reference binding](phase-16-reference-binding.md)
- [Phase 16.6 CREATE materialization](phase-16-create-materialization.md)
- [Phase 16.7A bulk UPDATE](phase-16-7a-bulk-update.md)
- [Phase 16.7B soft DELETE](phase-16-7b-soft-delete.md)
- [Phase 16.7C type migration](phase-16-7c-type-migration.md)
- [Phase 17A executable application flow](phase-17a-application-flow.md)
- [Phase 17B durable pending work](phase-17b-durable-pending-work.md)
- [Phase 17C local Git vault history](phase-17-git-vault-history.md)

## Completed pre-E2E phases

✅ **Phase 17D — append-first atomic facts + correction/removal semantics**

Before the first real E2E, refine the canonical entity-note body so ordinary knowledge is logically
atomic and append-first while the physical source of truth remains one Markdown note per entity.

```text
one entity Markdown note
        |
        +--> sparse current structured state when justified
        |
        `--> append-first atomic facts
                |
                +--> request-correlated provenance
                +--> human-visible capture chronology
                +--> exact/reliable duplicate suppression
                `--> targeted correction/removal when prior knowledge is false or explicitly deleted
```

This phase replaces the assumption that ordinary real-world transitions require destructive free-text
rewrites. A statement such as `Marta ahora trabaja en Thales` should normally become new canonical
knowledge without erasing the earlier Airbus knowledge. Explicit correction and removal remain special
mutation paths that may address an earlier fact safely.

Keep the representation minimal: a fact does not need its own unrelated UUID when a request-derived
locator such as `request_id + ordinal` is sufficient. Avoid event sourcing, universal historical/current
state flags, redundant per-fact timestamps, or Git SHAs embedded in facts unless implementation evidence
shows a concrete need. The human-readable note should still expose useful capture chronology while
preserving separately any real-world date supplied by the user.

The governing direction is documented in [Odyssey knowledge-model direction](knowledge-model-direction.md).
The earlier [Phase 17D temporal update semantics](phase-17d-temporal-update-semantics.md) preserves the
problem statement and evidence that motivated this refinement; implementation should reconcile that
contract with the simpler append-first model rather than continuing free-form temporal rewriting by
default.

✅ **Phase 17E — pre-E2E schema utility + retrieval validation checkpoint**

The schema utility/metadata review, retrieval benchmark, planner semantic-atomicity refinement, and
retrieval reduction/answer-path evidence are complete enough to enter the first real E2E without making
an unevidenced production retrieval change.

The schema review removed/deferred complexity that did not yet earn direct user value. Planner
semantic-atomicity was revalidated. Retrieval experiments established useful evidence but also exposed a
limitation in the previously assumed Combined Top-500 strategy.

The earlier adoption decision in PR #73 used an identity-unaware required-fact oracle and therefore
overstated Combined recall. The corrected identity-aware audit found Combined ALL-required recall of
72.7% / 81.8% / 86.4% / 90.9% / 90.9% at Top-100 / 200 / 300 / 400 / 500, with `scale-100` and
`scale-700` still missing required target-entity facts beyond Top-500. Production Combined is therefore
**not adopted at this checkpoint**; current whole-note retrieval remains production behavior.

Luna/none remains promising as a bounded relevance reducer when the required evidence is present in its
candidate set, but the remaining problem is upstream conjunctive/multi-fact candidate retrieval rather
than a reason to keep testing stronger-model combinations before E2E.

No further synthetic retrieval-strategy search is required before Phase 18. In particular, Odyssey will
not spend more pre-E2E benchmark effort on an entity-agnostic / "without entity" variant. A near-term
post-E2E hypothesis is preserved instead: decompose a search request into meaningful retrieval elements,
retrieve facts for each element, then reward canonical entities whose facts jointly cover more distinct
parts of the request. See [Future query-decomposed multi-fact retrieval](future-query-decomposed-retrieval.md).

Detailed Phase 17E evidence and decisions remain in:

- [Schema utility review](phase-17e-schema-utility-review.md)
- [Common metadata review](phase-17e-metadata-review.md)
- [Planner semantic-atomicity contract](phase-17e-planner-atomicity.md)
- [Retrieval adoption decision](phase-17e-retrieval-adoption.md) — historical decision superseded where
  the corrected identity-aware evidence invalidates its Top-500 recall premise
- [Retrieval reduction and answer-path evidence](phase-17e-retrieval-reduction-evidence.md)

## Current phase

➡️ **Phase 18 — n8n integration and first real end-to-end Odyssey use case**

Expose the stable application boundary through n8n and prove one real bounded write-then-read E2E now
that the 17D knowledge representation and 17E schema/retrieval checkpoint are settled. n8n remains
responsible for external triggers/integrations while domain behavior stays in `odyssey_core`.

The canonical [Phase 18 contract](phase-18-n8n-first-e2e.md) explicitly means **connect the already
adopted production path**, not promote every successful benchmark arm. Sol/low planning, current
whole-note MiniLM/context retrieval, existing bounded Luna write/fact-selection boundaries when their
approved contracts require them, Markdown persistence, pending work, and Git history are wired through
the real flow. Combined retrieval, a fixed Top-500 fact contract, the Luna retrieval reducer, query
decomposition, and Luna-first planner routing remain deferred.

The first E2E must also make derived-index freshness explicit: after a successful authoritative Markdown
mutation, refresh/rebuild the required local indexes so a second request through the same n8n boundary
can retrieve the newly written knowledge.

Phase 18.4 is the grounded consumer response contract: the runtime exposes bounded retrieval evidence
(stable identity, canonical type, provenance, and full human-readable content) for ChatGPT to formulate
the conversational response. Odyssey does not add a second answer-model call; standalone answer
generation remains future work in [Future extension points](future-extension-points.md).

⬜ **Phase 19 — end-to-end hardening, tracing, manual-edit ingestion, and evidence-driven refinements**

Harden the proven flow with repeatable integration/failure-path evidence, idempotency, operational
behavior, and measured performance. Add low-invasive operational tracing around real LLM,
persistence, and external boundaries rather than manual logging in every domain function.

Phase 17A already propagates `request_id`. Introduce a separate `trace_id` only if real retries or
subtraces prove that one logical request needs multiple operational traces.

Define direct user/Obsidian filesystem edits as a later ingestion boundary: detect external changes
without self-trigger loops, inspect/ingest the diff, preserve user wording where possible, normalize only
what is required, rebuild derived state, and audit through the normal request/Git boundary. Git remains
history/diff infrastructure rather than the always-on filesystem trigger.

Reassess semantic request history after the first real E2E. The product goal remains to answer questions
such as “what did I ask yesterday?” and “what changed when I told you Marta moved?”, but the earlier
proposal to add canonical `type=user_request` is deferred. Do not add that type or contaminate ordinary
knowledge resolution/retrieval before E2E evidence justifies the representation. Any future history
representation reuses `request_id` and never stores hidden model reasoning. See
[Future semantic request history](phase-17-request-records.md).

As an **early evidence-driven Phase 19 refinement**, revisit the query-decomposed multi-fact retrieval
hypothesis once the first real E2E supplies realistic retrieval cases. Test the smallest distinct-element
coverage rule before broader retrieval optimization or new infrastructure.

## Committed post-E2E product work

The following directions are **planned product work**, not optional ideas. Their exact phase numbers and
implementation order should be assigned after the first real E2E and Phase 19 hardening expose the right
boundaries; do not implement speculative infrastructure before then.

- ⬜ **Composable applications / capability dependencies:** Odyssey applications should be able to reuse
  lower-level capabilities or applications instead of reimplementing them independently. A target shape
  is `Reminders -> Tasks -> Projects`, with explicit dependencies and higher-level installation able to
  install/activate required dependencies. The first implementation should define the smallest safe
  dependency contract, prevent circular dependency graphs, and keep Odyssey Core as the shared canonical
  knowledge/write boundary.
- ⬜ **Multi-user shared knowledge and collaboration:** implement real shared knowledge after the Core/E2E
  boundary is stable. Use a shared household shopping/list scenario as an early validation case: one user
  can add missing items and another authorized user sees and can update the same shared knowledge promptly.
  This work must cover authentication, read/write authorization, private-vs-shared boundaries,
  synchronization/event propagation, conflict handling, and storage design before claiming privacy or
  collaboration guarantees. Preserve the private/local-memory direction, group principals, permission-
  filtered effective knowledge view, and sync/conflict guardrails defined in
  [Multi-user collaboration direction](multi-user-collaboration-direction.md).

## Conditional later work

The detailed cross-phase direction is centralized in
[Future extension points](future-extension-points.md). Important preserved directions include:

- 💡 **Odyssey platform boundary:** evolve toward a persistent knowledge layer used by humans,
  ordinary applications, and AI agents through Core + server interfaces such as HTTP and MCP. Canonical
  Markdown remains user/workspace-owned and storage-location agnostic rather than being required to live
  in a centrally hosted server. Domain applications/extensions, SDKs, deployment modes, and permissions
  remain later contracts after real E2E evidence. See [Odyssey platform direction](odyssey-platform-direction.md).
- 💡 **Local-first mobile runtime / standalone app:** preserve a future optional Android/iOS/client phase
  where canonical knowledge, derived SQLite indexes, deterministic analytics, and local MiniLM-style
  retrieval can execute on-device without making Odyssey Cloud mandatory. Server-backed sync/sharing and
  managed AI remain optional services. Evaluate secure account-connect/credential-broker patterns rather
  than embedding raw provider master keys in mobile apps. See
  [Future local-first mobile runtime](future-local-first-mobile-runtime.md).
- 💡 **Emergent schema coach:** after real usage justifies it, observe recurring knowledge patterns and
  propose types/properties in terms of the user capability they unlock. A future advisory
  `semantic_type_hint` for unresolved references may support deterministic counts of **distinct pending
  entity candidates** only after the hint has a stable normalization/validation contract; it is never a
  canonical type or creation authority. Require explicit approval and safe backfill/relinking rather than
  silent ontology growth. See [Future pending-reference evolution](future-pending-reference-evolution.md).
- 💡 **Human-in-the-loop:** build on Phase 17B durable pending work when ambiguity, dependency failure,
  partial success, or explicit user control requires clarification/approval.
- 💡 **Pending-reference relinking and recurrence:** preserve two separate signals: repeated occurrences
  of the same unresolved entity may justify proposing that entity, while many distinct unresolved
  entities sharing one normalized semantic type hint may justify proposing a new type/capability. Future
  relinking should address the exact source note + atomic fact + reference occurrence and re-render it
  deterministically; do not ask an LLM to search/replace arbitrary Markdown. Exact canonical name/alias
  evidence may authorize a relink; zero/multiple candidates remain pending/HITL. See
  [Future pending-reference evolution](future-pending-reference-evolution.md).
- 💡 **Mention-to-alias promotion:** keep current reference binding deterministic; add semantic alias
  promotion only under a separate evidenced contract.
- 💡 **Derived identity/link graph index:** extend the rebuildable index with aliases and
  wikilinks/backlinks only when graph execution is needed; Markdown remains authoritative.
- 💡 **Graph retrieval:** keep semantic-first relationship retrieval unless explicit structural queries
  or benchmarks justify bounded graph traversal.
- 💡 **Structured analytics / aggregations:** deterministic counts, sums, averages, and grouping over
  rebuildable structured/index data rather than loading the vault into an LLM.
- 💡 **App/capability delegation:** route planned delegated actions later through compact capability
  contracts; purchase/ticket, project, and translation workflows remain expected application families.
- 💡 **Type-aware writing profiles:** absent by default; add only when a note type demonstrates a real
  semantic body-organization need.
- 💡 **Generic tags:** Core stores and filters explicitly requested free-form tags; vocabulary and meaning remain user/app-owned, with no inference or registry.
- 💡 **Large-vault retrieval reduction:** retain high-recall local candidate retrieval and benchmark any
  selector before reducing strong-model context. The next preserved retrieval experiment is the
  [query-decomposed multi-fact retrieval hypothesis](future-query-decomposed-retrieval.md), not another
  pre-E2E search over arbitrary note/entity combinations.
- 💡 **Cost-aware request planning:** after the first real E2E exposes planner cost, benchmark Luna as a
  first-pass `PLAN | ESCALATE` planner with the current Sol/low planner as fallback. Reuse historical Luna
  failure cases as mandatory escalation evidence; adopt only if final planner quality matches the Sol
  baseline, unsafe non-escalation is strictly controlled, and total measured cost is materially lower.
- 💡 **Operational observability:** reconstruct planner/retrieval/resolution/persistence/n8n/LLM traces
  with safe usage/cost/error metadata, redaction, and retention controls once the E2E exists.
- 💡 **Performance/index optimization:** optimize only from measurements.
- 💡 **Proactive Memory/Context Layer:** non-disruptive resurfacing only after the direct E2E flow proves
  useful.

Git history, ADRs, benchmark records, branches, PRs, CI, and canonical architecture contracts remain
authoritative for what actually happened. This roadmap intentionally avoids duplicating those records.
