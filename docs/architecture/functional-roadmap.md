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

## Completed E2E phase

✅ **Phase 18 — n8n integration and first real end-to-end Odyssey use case**

Phase 18 is merged. The production path was connected through n8n and the thin persistent runtime to
`odyssey_core.execute_request()`. A real disposable WRITE created Marta, preserved unresolved Thales/Lyon
references as durable pending work, committed request-correlated Git history, and refreshed derived
indexes. A later independent READ through the same boundary recovered `Marta trabaja en Thales.` without
mutating canonical knowledge.

The grounded consumer contract is settled independently of any specific frontend: Odyssey returns stable
identity/type/provenance plus full retrieved content, and an external consumer may formulate the
conversational response without another answer call inside Core. Phase 20 will add the first standalone
Odyssey consumer. See the canonical [Phase 18 contract](phase-18-n8n-first-e2e.md).

## Current phase

➡️ **Phase 19 — end-to-end hardening**

The canonical [Phase 19 contract](phase-19-e2e-hardening.md) hardens the proven Phase 18 path before the
first standalone web product surface.

```text
19.0  contract + hardening matrix                         ✅ complete on merge
19.1  retry / duplicate / failure-path safety             ➡️ next
19.2  bounded tracing + timing + usage/cost                ⬜
```

The immediate reliability question is narrower than semantic duplicate suppression: one logical
delivery must not accidentally become two mutations merely because infrastructure retried it, while a
genuine second user request must remain meaningful. Phase 19.1 will inspect actual n8n/runtime retry
behavior before choosing an idempotency mechanism. The first evidence correction preserves an optional
delivery-owned `request_id` through n8n and the runtime into Core; it does not deduplicate by text or
add persistent idempotency infrastructure. See the [Phase 19 contract](phase-19-e2e-hardening.md).

Operational tracing stays low-invasive and `request_id` remains the default correlation key. Add a
separate `trace_id` only if real retries/subtraces prove it necessary.

Reassess semantic request history during Phase 19 rather than automatically creating a canonical
`type=user_request`. Any future representation reuses `request_id` and never stores hidden model
reasoning. See [Future semantic request history](phase-17-request-records.md).

## Next product phase

⬜ **Phase 20 — Odyssey Online MVP: standalone answerer + mobile web**

After 19.1/19.2 make the existing path dependable and diagnosable, build the smallest useful standalone
Odyssey consumer for a phone browser. See the canonical [Phase 20 contract](phase-20-odyssey-online-mvp.md).

```text
20.0  consumer contract + architecture challenge             ⬜
20.1  grounded answerer benchmark                            ⬜
20.2  minimal mobile web frontend                            ⬜
20.3  protected Raspberry/Cloudflare deployment + E2E        ⬜
```

The answerer benchmark starts with Luna as the preferred inexpensive candidate but must adopt a model
only from grounded quality/cost evidence. Sol remains a quality reference rather than the automatic
production answerer. Deterministic write acknowledgements should avoid an unnecessary model call when
existing result fields are sufficient.

The MVP is a normal mobile web page with a text field, submit behavior, loading/error state, and rendered
response. Android voice input is supplied by ordinary Gboard dictation through that text field; Odyssey
does not add microphone recording or a speech-to-text service for the MVP.

The Internet-facing surface must be protected before it can reach personal knowledge. The planned shape
uses the existing Raspberry/Cloudflare deployment with a separate Odyssey hostname and a narrow access
policy. Actual Cloudflare/security changes and real-vault activation remain explicit human-approved
deployment actions.

## Committed post-E2E product work

The following directions are **planned product work**, not optional ideas. Their exact later phase numbers
should be assigned from real Odyssey Online usage rather than speculative infrastructure work.

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

- 💡 **Direct Markdown / Obsidian edit ingestion:** detect external user edits without self-trigger loops,
  preserve safe user wording, normalize only what canonical contracts require, refresh derived state, and
  audit accepted changes through the normal request/Git safeguards. Real Odyssey Online usage now takes
  priority so this ingestion boundary can be designed from actual editing needs.
- 💡 **Odyssey platform boundary:** evolve toward a persistent knowledge layer used by humans,
  ordinary applications, and AI agents through Core + server interfaces such as HTTP and MCP. Canonical
  Markdown remains user/workspace-owned and storage-location agnostic rather than being required to live
  in a centrally hosted server. Domain applications/extensions, SDKs, deployment modes, and permissions
  remain later contracts after real E2E evidence. See [Odyssey platform direction](odyssey-platform-direction.md).
- 💡 **Local-first mobile runtime / native standalone app:** Phase 20 is a server-backed mobile web MVP,
  not the future optional Android/iOS local runtime. Preserve the later direction where canonical
  knowledge, derived SQLite indexes, deterministic analytics, and local MiniLM-style retrieval can execute
  on-device without making Odyssey Cloud mandatory. Server-backed sync/sharing and managed AI remain
  optional services. See [Future local-first mobile runtime](future-local-first-mobile-runtime.md).
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
  [query-decomposed multi-fact retrieval hypothesis](future-query-decomposed-retrieval.md), now intentionally
  scheduled after realistic Odyssey Online usage exposes concrete misses.
- 💡 **Cost-aware request planning:** after the first real E2E exposes planner cost, benchmark Luna as a
  first-pass `PLAN | ESCALATE` planner with the current Sol/low planner as fallback. Reuse historical Luna
  failure cases as mandatory escalation evidence; adopt only if final planner quality matches the Sol
  baseline, unsafe non-escalation is strictly controlled, and total measured cost is materially lower.
- 💡 **Performance/index optimization:** optimize only from measurements.
- 💡 **Proactive Memory/Context Layer:** non-disruptive resurfacing only after the direct E2E flow proves
  useful.

Git history, ADRs, benchmark records, branches, PRs, CI, and canonical architecture contracts remain
authoritative for what actually happened. This roadmap intentionally avoids duplicating those records.
