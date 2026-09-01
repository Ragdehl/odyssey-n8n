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

## Completed phase

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

## Current phase

➡️ **Phase 17E — pre-E2E schema utility + retrieval validation**

Before n8n/E2E integration, challenge the initial schema and retrieval assumptions against the product
model established in 17D.

### ✅ Phase 17E schema utility and metadata review — completed

The type/property and common-metadata reviews are complete. Their detailed decisions remain in the
[schema utility review](phase-17e-schema-utility-review.md) and [common metadata review](phase-17e-metadata-review.md).

### ✅ Phase 17E retrieval benchmark — evidence completed

Review every current canonical type and property and classify it as `KEEP`, `DEFER`, or `REMOVE` based
primarily on **direct user value**, not internal token savings. A type/property earns its complexity when
it unlocks a recurring user-visible view, action, filter, comparison, calculation, automation, or domain
behavior that ordinary facts cannot provide as well.

Preserve the future emergent-schema direction without implementing a generic schema engine yet:
Odyssey may later detect repeated knowledge patterns and propose a useful new type/property in ordinary
product language, but schema mutation requires explicit user approval. A later approved promotion must
be able to backfill existing knowledge and safely relink historical mentions to newly canonical entities
using normal identity/reference safety; ambiguous mentions remain unresolved/pending rather than being
blindly rewritten.

Benchmark the existing whole-note MiniLM strategy against fact-level and combined entity+fact retrieval.
This is a retrieval experiment only. Previous fragment-level evidence showed that smaller fragments can
increase semantic similarity but are **not safe autonomous write authority**; do not forget or overextend
that result.

Measure recall, practical Top-K behavior, long-note dilution, Spanish/French/contextual cases, stronger-
model input-token reduction, latency, and local resource cost before changing production retrieval.
Do not replace the current local MiniLM model merely because another model might be stronger; first test
whether the better retrieval unit itself solves the observed dilution problem.

See [Odyssey knowledge-model direction](knowledge-model-direction.md) for the canonical rationale and
migration/relinking constraints.

### ✅ Phase 17E planner semantic-atomicity refinement — completed

The retrieval benchmark is complete as evidence. Its leading Combined candidate remains unadopted;
whole-note retrieval remains production behavior. The focused current subphase validates whether the
production Sol/low planner preserves semantic atomicity: independently meaningful facts should split,
while coherent explanations, reflections, and decisions with dependent reasons should remain unified.
See the [planner semantic-atomicity contract](phase-17e-planner-atomicity.md). Planner revalidation
succeeded; the remaining retrieval adoption decision is separate and does not authorize production
retrieval changes by itself.

### ✅ Phase 17E retrieval adoption decision — completed focused subphase

The evidence-backed decision adopts Combined whole-note + atomic-fact retrieval with a local
Top-500 candidate width and the already-tested fixed reciprocal-rank fusion (`RRF_K = 60`). Top-300
remains the lean fallback candidate for later real E2E measurement. See the
[retrieval adoption decision](phase-17e-retrieval-adoption.md).

Production Combined retrieval is not implemented by this decision; whole-note behavior remains current
production behavior until the remaining reduction evidence and the separate implementation PR are
reviewed and merged.

### ➡️ Phase 17E retrieval reduction + answer-path evidence — current focused subphase

Top-500 proves broad candidate recall, but a relevant required fact can appear deep in the fused ranking.
A small final `context_limit` therefore cannot safely be implemented as simple rank truncation without
potentially erasing the recall gain. Before production Combined wiring, compare deterministic truncation
with a bounded high-recall Luna fact-locator selector that can explicitly escalate instead of guessing.
Then run a compact live `retrieval -> grounded facts -> Sol` answer-path check and measure required-fact
retention, answer quality, provider tokens/cost, latency, and escalation behavior. See the
[retrieval reduction evidence contract](phase-17e-retrieval-reduction-evidence.md).

The following step, only after this evidence closes the final-context policy, is the bounded production
Combined implementation in `ContextIndex` / `get_context`. Phase 18 remains blocked until that production
checkpoint is merged.

⬜ **Phase 18 — n8n integration and first real end-to-end Odyssey use case — next after Phase 17E is settled**

Expose the stable application boundary through n8n and prove one real bounded E2E use case **after** the
17D knowledge representation and 17E schema/retrieval checkpoint are settled. n8n remains responsible
for external triggers/integrations while domain behavior stays in `odyssey_core`.

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
- 💡 **Emergent schema coach:** after real usage justifies it, observe recurring knowledge patterns and
  propose types/properties in terms of the user capability they unlock; require explicit approval and
  safe backfill/relinking rather than silent ontology growth.
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
- 💡 **Generic tags:** Core stores and filters explicitly requested free-form tags; vocabulary and meaning remain user/app-owned, with no inference or registry.
- 💡 **Large-vault retrieval reduction:** retain high-recall local candidate retrieval and benchmark any
  selector before reducing strong-model context.
- 💡 **Operational observability:** reconstruct planner/retrieval/resolution/persistence/n8n/LLM traces
  with safe usage/cost/error metadata, redaction, and retention controls once the E2E exists.
- 💡 **Performance/index optimization:** optimize only from measurements.
- 💡 **Proactive Memory/Context Layer:** non-disruptive resurfacing only after the direct E2E flow proves
  useful.

Git history, ADRs, benchmark records, branches, PRs, CI, and canonical architecture contracts remain
authoritative for what actually happened. This roadmap intentionally avoids duplicating those records.
