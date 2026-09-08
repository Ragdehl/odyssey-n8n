# Functional Roadmap

This is Odyssey's canonical source for **functional implementation status, intended order, and the next adoption gate**. Detailed contracts and historical evidence live in linked phase documents, ADRs, and benchmarks rather than being copied here.

Status: ✅ **IMPLEMENTED** · ➡️ **NEXT** · ⬜ **PLANNED** · 💡 **LATER / CONDITIONAL**

## Completed foundation

| Phase | Result |
| --- | --- |
| 9 | Deterministic exact entity resolution by canonical name/alias. |
| 10 | Local semantic entity candidate retrieval; similarity is evidence only. |
| 11 | Contextual/hybrid existing-entity resolution with deterministic Core validation. |
| 12 | Explicit deterministic entity persistence primitives. |
| 13 | General knowledge context retrieval (`get_context`) over rebuildable local indexes. |
| 14 | Validated top-level `RequestPlan` interpretation. |
| 15–15.3 | Semantic write planning, schema-aware selection/mutations, explicit links/tags, generic delegation preservation. |
| 16–16.7C | Safe create/update targeting, bounded UPDATE writing, deterministic CREATE, reference binding, bulk UPDATE, soft DELETE, and type migration. |
| 17A–17C | Executable Core application flow, durable pending work, and request-correlated local Git history. |
| 17D | Append-first atomic facts with request-derived fact locators and targeted correction/removal. |
| 17E | Pre-E2E schema/retrieval validation; unevidenced Combined Top-500 adoption withdrawn after identity-aware correction. |
| 18 | First real n8n -> runtime -> Core WRITE/READ end-to-end path. |
| 19 | Retry/failure hardening plus bounded timing/provider-usage evidence. |

Canonical/historical detail remains in the phase documents under this directory and in [Architecture Decisions](../decisions/README.md). The [Architecture Overview](overview.md) describes the current composed system without replaying this history.

## Current phase — Phase 20: Odyssey Online MVP

Goal: deliver the smallest useful standalone Odyssey experience in a phone browser, then let real usage drive improvements.

See [Phase 20 — Odyssey Online MVP](phase-20-odyssey-online-mvp.md).

```text
20.0  consumer contract + architecture challenge             ✅ complete
20.1A offline grounded-answerer benchmark preparation        ✅ complete
20.1B focused live answerer model evidence                    ✅ complete
20.2A mobile web source + offline deterministic checks        ✅ complete
20.2B real n8n serving + Chrome Android validation            ➡️ next
20.2C planner incident hardening + focused live gate          ➡️ next
20.3  protected Raspberry/Cloudflare deployment + E2E        ⬜
```

### 20.1B — answerer adoption gate

Run the frozen live answerer cases when the Raspberry/provider environment is available. Start with the inexpensive Luna candidate, compare a materially cheaper candidate, and keep Sol as a quality reference rather than an assumed production default. Adoption requires grounded, useful answers without material hallucination or evidence loss.

See [Phase 20.1 grounded-answerer benchmark](phase-20-1-grounded-answerer-benchmark.md).

### 20.2B — real browser integration

Serve the checked-in `odyssey_web/` surface through the adopted n8n-facing product boundary and validate the real request/response flow in Chrome on Android. The merged 20.2A checkpoint already proves browser-side request identity, retry, validation, and UI behavior offline; 20.2 is not complete until the environment-backed integration works.

### 20.2C — planner incident hardening

Before production adoption, complete the bounded deterministic planner hardening and explicitly
authorize its focused Sol/low live evidence gate. See [Planner incident hardening](planner-incident-hardening.md).

### 20.3 — protected deployment

Before personal knowledge/provider actions are reachable from the Internet, protect the Odyssey hostname with an explicit access-control boundary. Use disposable data for first integration evidence and keep real-vault activation human controlled. Cloudflare/security/network changes require explicit approval.

## Committed post-MVP directions

These are real product directions, but their exact implementation order should follow evidence from Odyssey Online usage rather than speculative phase numbering.

### Composable applications and capabilities

Applications should reuse shared Odyssey knowledge and lower-level capabilities rather than creating isolated stores or duplicate semantics. A useful target is composition such as:

```text
Reminders <- Tasks <- Projects
```

The first real application should define the smallest dependency/routing contract from evidence. Core remains the safe knowledge/write boundary. See [Future Extension Points](future-extension-points.md) and [Odyssey Platform Direction](odyssey-platform-direction.md).

### Multi-user shared knowledge

Support private and selectively shared knowledge only after authentication, authorization-before-retrieval, synchronization, conflict, and storage boundaries are explicit. A shared household list is an early concrete validation scenario.

See [Multi-user Collaboration Direction](multi-user-collaboration-direction.md).

## Later / conditional directions

The detailed index is [Future Extension Points](future-extension-points.md). Important preserved directions include:

- 💡 **Retrieval refinement from real misses:** first test query-decomposed multi-fact/entity-coverage retrieval; only then add candidate reduction or compact evidence if measured cost/volume justifies it. See [Future retrieval refinements](future-query-decomposed-retrieval.md).
- 💡 **Pending-reference evolution / schema coaching:** safely relink exact attributable occurrences and use repeated unresolved patterns only as advisory evidence for future schema proposals. See [Future pending-reference evolution](future-pending-reference-evolution.md).
- 💡 **Product help + bounded conversation context:** isolate Odyssey help from personal retrieval and keep ordinary recent conversation ephemeral unless explicitly remembered. See [Future Odyssey help and conversation context](future-help-and-conversation-context.md).
- 💡 **Usage/cost observability:** project already-collected safe operational/provider evidence into simple and advanced product views without creating a second tracing authority. See [Future product usage observability](future-product-usage-observability.md).
- 💡 **Capture-context provenance:** optional location/context belongs to fact/request provenance, not entity properties. See [Future capture-context provenance](future-capture-context-provenance.md).
- 💡 **Platform/local-first portability:** keep Core/data contracts usable by self-hosted, future local/mobile, app, and agent clients without making a central Odyssey server semantically mandatory. See [Odyssey Platform Direction](odyssey-platform-direction.md).
- 💡 **Direct Markdown/Obsidian edit ingestion:** eventually recognize authorized external edits, avoid self-trigger loops, validate only required normalization, refresh derived state, and audit accepted changes.
- 💡 **Structured analytics:** deterministic counts/sums/grouping over rebuildable structured/index data; do not load the whole vault into an LLM for arithmetic.
- 💡 **Cost-aware planning:** benchmark Luna `PLAN | ESCALATE` to the existing strong planner only if real planner cost distribution makes the optimization worthwhile.
- 💡 **Proactive resurfacing:** non-disruptive reminders/context suggestions only after direct usage demonstrates value.
- 💡 **Performance/index optimization:** optimize from measurements, not anticipated scale.

## Roadmap rule

This file records **current status and intended sequencing**, not every implementation detail. When a phase completes, update the status here and leave its detailed contract/evidence in the phase document, ADR, tests, and benchmark records. Do not duplicate those historical narratives back into the roadmap.
