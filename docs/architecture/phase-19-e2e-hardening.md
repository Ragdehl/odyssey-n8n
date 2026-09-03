# Phase 19 — E2E hardening

Status: **Phase 19.0 contract complete on merge; Phase 19.1 is next**

## Objective

Turn the Phase 18 write-then-read proof into a dependable operating path before exposing Odyssey through the first standalone web product surface.

Phase 18 proved that one real request can enter through n8n, reach the persistent runtime and Core, mutate canonical Markdown, preserve pending work and Git history, refresh derived indexes, and later retrieve that knowledge. Phase 19 asks the narrower reliability question: **what happens when that same proven path is retried, interrupted, duplicated, partially unavailable, restarted, or measured under realistic use?**

The first priority is reliability and diagnosability of the already-adopted path, not new user capability.

```text
Phase 18
happy-path E2E works
        |
        v
Phase 19
make the same path dependable
        |
        +--> retry / duplicate safety
        +--> failure-path evidence
        +--> bounded operational tracing
        `--> timing + usage/cost
        |
        v
Phase 20
standalone Odyssey Online MVP
```

Direct Markdown/Obsidian edit ingestion and retrieval refinement remain intended later work, but they no longer block the first usable standalone Odyssey product. Real usage through Phase 20 should provide better evidence for both.

## Architecture challenge

Result: **PROCEED**.

The observed problem is operational reliability and diagnosability of the existing E2E. The simplest solution is to harden current n8n/runtime/Core boundaries rather than introduce a new orchestrator, database, queue, tracing service, graph layer, or retrieval strategy.

Existing responsibilities remain appropriate:

- n8n owns external orchestration/integration;
- the thin runtime owns process/HTTP adaptation and provider/environment composition;
- `odyssey_core` owns semantic execution and canonical mutation rules;
- Markdown remains authoritative knowledge;
- SQLite indexes remain derived/rebuildable;
- Git remains request-correlated history, not the source of truth or filesystem event bus;
- `request_id` remains the logical-request correlation identifier unless concrete retry/subtrace evidence proves a separate `trace_id` is necessary.

Do not solve hypothetical distributed-system problems before the single-user local runtime demonstrates them.

## Phase sequence

```text
19.0  contract + hardening matrix                         ✅ complete on merge
19.1  retry / duplicate / failure-path safety             ➡️ next
19.2  bounded tracing + timing + usage/cost                ⬜
```

### 19.0 — contract and hardening matrix

Define the observed failure/retry surfaces and the evidence required before implementation. No production behavior change is required merely to complete 19.0.

### 19.1 — retry, duplicate, and failure-path safety

Harden the existing n8n -> runtime -> Core path against realistic repeated or interrupted delivery.

This subphase must first establish actual current behavior before choosing an idempotency mechanism. Do **not** move `request_id` ownership, add an idempotency database, queue, or distributed lock without evidence that the existing contracts cannot solve the observed case simply.

At minimum investigate and classify:

- identical user request submitted twice intentionally;
- transport/client retry after a timeout where the caller does not know whether Core committed;
- runtime failure before Core execution;
- provider/planner failure before mutation;
- failure during or after canonical Markdown mutation;
- Git-history failure after a valid Markdown mutation;
- index-refresh failure after a valid Markdown mutation;
- pending-work persistence failure after partial execution;
- process restart between independent requests.

The desired invariant is not “every repeated sentence is ignored.” A legitimate repeated user statement may be meaningful. The goal is narrower: **one logical delivery must not accidentally become two semantic mutations merely because infrastructure retried it.** Phase 19.1 resolves the delivery-boundary contract from the observed n8n/runtime behavior below without introducing blanket semantic deduplication.

#### Phase 19.1 baseline and bounded identity correction

The current development workflow was inspected before changing the delivery contract. Its HTTP
Request node has a 120-second timeout and does not configure `retryOnFail`; the compose-level n8n
container restart policy is `unless-stopped`, not a per-request retry policy. Therefore n8n does not
currently retry this node automatically from the checked-in workflow configuration. A caller can
still retry after a timeout or lost response, so that transport case remains material.

Before the correction, `/execute` accepted only `{ "request": "..." }`, and Core generated a new
UUID inside `execute_request()` for every call. Repeating the same payload therefore produced a new
logical `request_id`, even when the caller was retrying one uncertain delivery. The same text submitted
by a genuinely new n8n execution was indistinguishable from that retry at the Core boundary.

The smallest adopted correction reuses the existing request identity rather than adding a deduplication
store:

```text
n8n execution
    |
    +--> request_id = supplied stable ID, or n8n-<execution.id>
    |
    `--> {request, request_id} -> runtime -> execute_request(request_id_factory=...)
```

The runtime accepts an optional bounded `request_id` and rejects unsafe path/control characters before
Core. The checked-in workflow uses the n8n execution ID when the caller does not supply one; retries
of the same execution therefore preserve identity, while separate executions receive different IDs.
An upstream caller retrying by starting a new execution must provide the original ID if it needs the
same logical-delivery identity. Core's existing exact duplicate/idempotent structured materialization
guards remain responsible for safe repeated semantic operations; identical user text is never used as
a blanket deduplication key.

The deterministic evidence matrix for this correction is:

| Surface | Evidence and current outcome |
| --- | --- |
| Normal WRITE/READ | Existing Core/application and runtime boundary tests cover one request ID, mutation/index refresh, and non-mutating retrieval. |
| Same text, intentional duplicate | Boundary regression sends two different delivery IDs; both reach Core and remain distinguishable. |
| Same delivery retry | Boundary regression sends the same delivery ID twice; both attempts preserve that identity for Core, without semantic text deduplication. |
| Invalid/runtime failure | HTTP validation returns 400 without Core; Core/runtime and serialization failures return bounded 500. |
| Planner/provider failure | Application tests return failed evidence before mutation and do not record pending work. |
| Markdown then Git failure | Existing history tests show Markdown remains and history reports `FAILED`; Git is not authority. |
| Markdown then index failure | Runtime composition refresh occurs after Core; a refresh exception remains an explicit runtime failure while Markdown remains authoritative/rebuildable. |
| Partial/pending failure | Existing pending tests preserve partial application evidence and report pending durability failure separately. |
| Restart | Existing persistent-runtime tests rebuild disposable derived indexes from the configured repository; canonical Markdown is not process state. |

No live provider call was needed: the identity and failure behavior are boundary contracts covered by
deterministic injected providers. Docker API inspection confirmed the development n8n container is
running, but no workflow execution or real vault operation was performed for this evidence-first step.

### 19.2 — bounded operational tracing, timing, and usage/cost

Add enough low-invasive evidence to reconstruct what happened at important external/expensive boundaries without logging every domain function.

Preferred trace shape:

```text
request_id
   |
   +--> planner/model boundary
   +--> retrieval/resolution boundary
   +--> canonical persistence outcome
   +--> pending outcome
   +--> Git outcome
   +--> index refresh
   `--> runtime/n8n result
```

Capture only useful bounded metadata such as stage, outcome, duration, safe error category, model/configuration identity where already public to the application, and provider usage/cost when reliably available. Do not store prompts, hidden reasoning, credentials, or unrestricted user content merely for observability.

A separate `trace_id` is not introduced by default. Add one only if a real logical `request_id` demonstrably spans multiple operational attempts/subtraces that cannot be represented safely otherwise.

## Hardening evidence matrix

Phase 19 implementation should accumulate evidence against this matrix rather than treating a single HTTP 200 as success.

| Surface | Evidence expected |
| --- | --- |
| Normal WRITE | one intended canonical mutation, pending/Git/index outcomes explicit |
| Normal READ | grounded retrieval, no canonical mutation |
| Client/transport retry | no accidental duplicate mutation for one logical delivery |
| Duplicate intentional request | behavior distinguished from infrastructure retry; no blanket semantic dedupe |
| Planner/provider failure | no mutation; bounded failure evidence |
| Canonical write failure | fail closed with authoritative state inspectable |
| Git failure | Markdown authority preserved; history failure explicit |
| Index refresh failure | Markdown authority preserved; stale/failed derived state explicit and recoverable |
| Pending persistence failure | partial/incomplete work reports durable-state failure explicitly |
| Runtime restart | canonical Markdown survives; derived state can rebuild; pending/Git remain inspectable |
| Empty/no-result READ | explicit grounded empty evidence, not invented answer |

Exact test cases may evolve as implementation exposes the real boundaries, but the invariants above should remain visible.

## Acceptance criteria

Phase 19 is complete when observable evidence demonstrates all of the following:

1. the Phase 18 E2E remains functional through the unchanged canonical n8n/runtime/Core boundaries;
2. realistic retry/duplicate behavior has an explicit tested contract and cannot accidentally double-apply one logical delivery;
3. important failure paths preserve Markdown authority and return bounded, diagnosable outcomes;
4. runtime restart/rebuild behavior is tested without making SQLite or process memory authoritative;
5. operational tracing can correlate the important stages of a request using `request_id` without exposing secrets or hidden reasoning;
6. useful stage timing and provider usage/cost are recorded when technically available, with absence represented explicitly rather than fabricated;
7. no separate `trace_id` or new observability infrastructure is introduced unless concrete evidence justifies it;
8. deterministic tests, focused environment evidence where required, CI, semantic review, and human merge are green for each subphase.

## Deferred beyond Phase 19

### Direct Markdown / Obsidian edit ingestion

Direct user filesystem edits remain a separate future ingestion boundary. Its eventual contract must distinguish Odyssey-authored changes from external edits, avoid self-trigger loops, preserve user wording where safe, validate/normalize only what canonical contracts require, refresh derived state, and audit accepted canonical changes through normal request/Git safeguards. Git may help inspect/audit diffs but must not become the always-on filesystem trigger by assumption.

### Evidence-driven retrieval refinement

The preserved query-decomposed multi-fact hypothesis remains valid future work, but adoption should wait for realistic misses from actual Odyssey usage. Start with the smallest experiment, benchmark against current whole-note production behavior, and do not activate Combined, fixed Top-500 facts, Luna retrieval reduction, graph retrieval, or new vector infrastructure by default.

## Out of scope

Phase 19 does not by itself authorize:

- the standalone answer-generation model or Odyssey Online frontend planned for Phase 20;
- public Internet exposure, authentication, or Cloudflare security changes;
- multi-user sync, ACLs, or shared storage;
- direct Markdown/Obsidian edit ingestion;
- retrieval-strategy changes;
- automatic ontology/schema growth;
- pending-reference relinking/HITL implementation;
- composable application dependency infrastructure;
- LangGraph or another orchestrator;
- a new authoritative database/vector database;
- a general event-sourcing architecture;
- changing Markdown as the source of truth.

Those directions remain in their roadmap/future-extension contracts. Phase 20 has its own planned contract and security gate.

## Open decisions

1. **Retry identity / idempotency key:** determine in 19.1 from actual n8n/runtime retry behavior. Do not assume `request_id` should move outside Core.
2. **Observability persistence:** choose the smallest safe representation in 19.2 after identifying which evidence is not already available from application results, Git, n8n executions, and provider responses.
3. **Separate `trace_id`:** default is **no**; reconsider only if one logical request requires multiple distinguishable operational attempts.

## Immediate next step

Proceed to **Phase 19.1** after this contract PR is merged. The first implementation task is to inspect the current n8n/runtime/Core behavior under duplicate/retry/failure scenarios and design the smallest idempotency/failure-path correction from evidence. Raspberry/n8n environment access materially improves reliability for that work, so implementation should route to Codex when the environment is available.

After 19.1 and 19.2 are complete, proceed to the planned [Phase 20 Odyssey Online MVP](phase-20-odyssey-online-mvp.md) before returning to direct Obsidian ingestion or retrieval refinement.
