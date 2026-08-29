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

Canonical detail for these completed phases lives in:

- [Phase 15 planning contract](phase-15-write-planning.md)
- [Phase 16 writing checkpoint](phase-16-writing.md)
- [Phase 16 reference binding](phase-16-reference-binding.md)
- [Phase 16.6 CREATE materialization](phase-16-create-materialization.md)
- [Phase 16.7A bulk UPDATE](phase-16-7a-bulk-update.md)
- [Phase 16.7B soft DELETE](phase-16-7b-soft-delete.md)
- [Phase 16.7C type migration](phase-16-7c-type-migration.md)

## Current phase

✅ **Phase 17A — executable Core application flow + stable `request_id`**

Compose the already-validated planner, retrieval, target/reference preflight, CREATE/UPDATE/DELETE/type
migration, and deterministic bulk UPDATE primitives into one small application boundary that can execute
one logical user request and return a stable typed result.

```text
raw request
    |
    v
validated RequestPlan
    |
    v
17A application executor
    |
    +--> retrieve
    +--> bounded writes
    +--> cross-unit dependencies
    +--> deterministic bulk UPDATE
    `--> typed deferred/delegated evidence
```

Phase 17A introduces one stable `request_id` per logical request. The same identifier is intentionally
reused later by durable pending work, Git history, semantic request history, and operational tracing.
It is generated once at the application boundary, not once per action or note.

17A is a **composition boundary, not a generic workflow engine**. It reuses existing Core primitives
rather than reimplementing their semantics.

Ordinary 17A automated tests use deterministic fakes/mocks/stubs for Sol, contextual reasoning, Luna,
and other model/external boundaries. Normal pytest/CI must run without OpenAI credentials or network,
spend no model tokens, and never depend on model variability. Live evidence is required only if a
production model-facing contract materially changes, following `AGENTS.md`.

See the canonical [Phase 17A executable application-flow contract](phase-17a-application-flow.md).

Implementation lives in `odyssey_core.application.execute_request()`. It composes the existing planner,
retrieval, reference-preflight/binding, materialization, deterministic bulk UPDATE, and delegation
boundaries without adding a workflow engine. One generated `request_id` is returned through the typed
application result for every outcome.

## Remaining intended sequence

✅ **Phase 17B — durable pending work**

Persist actionable incomplete post-plan work so ambiguity, dependency failures, failed/deferred targets,
partial bulk failures, and delegated work survive process exit without semantic reconstruction. Reuse the
17A `request_id` and preserve the validated incomplete action together with typed execution evidence.

Keep this state outside canonical knowledge. The approved Phase 17B storage boundary uses
`/data/odyssey/state/pending/` as durable non-knowledge application state and deterministic JSON,
not canonical Markdown notes. This avoids adding ontology types or exclusions to vault scanning,
indexing, resolution, and bulk membership. A fully completed request creates no pending record; a
planning failure before a valid `RequestPlan` is operational failure rather than Phase 17B state.
Pending-persistence failure must be explicit and must not roll back successful note mutations.

See the canonical [Phase 17B durable pending-work contract](phase-17b-durable-pending-work.md).

➡️ **Phase 17C — local Git history per logical request**

Add the smallest local Git adapter around the authoritative Markdown vault. Per-note materializers
remain unaware of Git. Prefer one local commit for the successful Markdown mutations caused by one
logical request and correlate it through:

```text
Odyssey-Request: <request_id>
```

Git remains audit/history/recovery infrastructure, never source of truth. Remote backup, automatic
push/pull, and multi-device conflict handling remain separate operational decisions. See
[Phase 17C local Git vault history](phase-17-git-vault-history.md).

⬜ **Phase 17D — temporal knowledge preservation and correction semantics**

Before the first real E2E, distinguish **corrections of false knowledge** from **real-world state
transitions**. A transition such as `Marta ha dejado Airbus y ahora trabaja en Thales` should update the
current structured property while preserving the prior true Airbus fact as canonical historical
knowledge. A correction such as `me equivoqué: Marta nunca trabajó en Airbus` may remove or replace the
false fact under the existing safety rules.

Do not rely on Git history as the only place where past truth survives, and do not introduce generic
event sourcing. Preserve explicit dates when supplied and do not invent unsupported temporal precision.
See [Phase 17D temporal update semantics](phase-17d-temporal-update-semantics.md).

⬜ **Phase 18 — n8n integration and first real end-to-end Odyssey use case**

Expose the stable application boundary through n8n and prove one real bounded E2E use case. n8n remains
responsible for external triggers/integrations while domain behavior stays in `odyssey_core`.

⬜ **Phase 19 — end-to-end hardening, tracing, and evidence-driven history refinements**

Harden the proven flow with repeatable integration/failure-path evidence, idempotency, operational
behavior, and measured performance. Add low-invasive operational tracing around real LLM,
persistence, and external boundaries rather than manual logging in every domain function.

Phase 17A already propagates `request_id`. Introduce a separate `trace_id` only if real retries or
subtraces prove that one logical request needs multiple operational traces.

Reassess semantic request history after the first real E2E. The product goal remains to answer questions
such as “what did I ask yesterday?” and “what changed when I told you Marta moved?”, but the earlier
proposal to add canonical `type=user_request` is deferred. Do not add that type or contaminate ordinary
knowledge resolution/retrieval before E2E evidence justifies the representation. Any future history
representation reuses `request_id` and never stores hidden model reasoning. See
[Future semantic request history](phase-17-request-records.md).

## Conditional later work

The detailed cross-phase direction is centralized in
[Future extension points](future-extension-points.md). Important preserved directions include:

- 💡 **Odyssey platform boundary:** evolve toward a persistent knowledge layer used by humans,
  ordinary applications, and AI agents through Core + server interfaces such as HTTP and MCP. Canonical
  Markdown remains user/workspace-owned and storage-location agnostic rather than being required to live
  in a centrally hosted server. Domain applications/extensions, SDKs, deployment modes, and permissions
  remain later contracts after real E2E evidence. See [Odyssey platform direction](odyssey-platform-direction.md).
- 💡 **Human-in-the-loop:** build on Phase 17B durable pending work when ambiguity, dependency failure,
  partial success, or explicit user control requires clarification/approval.
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
- 💡 **Tag vocabulary evolution:** keep explicit-only controlled tags until evidence justifies change.
- 💡 **Large-vault retrieval reduction:** retain high-recall local candidate retrieval and benchmark any
  selector before reducing strong-model context.
- 💡 **Operational observability:** reconstruct planner/retrieval/resolution/persistence/n8n/LLM traces
  with safe usage/cost/error metadata, redaction, and retention controls once the E2E exists.
- 💡 **Multi-user ownership/sharing:** design authentication, authorization, and storage boundaries first.
- 💡 **Performance/index optimization:** optimize only from measurements.
- 💡 **Proactive Memory/Context Layer:** non-disruptive resurfacing only after the direct E2E flow proves
  useful.

Git history, ADRs, benchmark records, branches, PRs, CI, and canonical architecture contracts remain
authoritative for what actually happened. This roadmap intentionally avoids duplicating those records.
