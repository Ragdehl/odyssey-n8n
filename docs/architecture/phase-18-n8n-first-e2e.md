# Phase 18 — n8n integration and first real Odyssey E2E

Status: **current phase contract; Phase 18.2 checkpoint blocked by provider quota**

## Objective

Connect the already-adopted Odyssey production boundaries into one real Raspberry Pi flow exposed through n8n, then prove that knowledge can be written, persisted, re-indexed, retrieved, and returned through the same external boundary.

Phase 18 is an **integration phase**, not a retrieval-strategy redesign.

```text
external request
      |
      v
     n8n
      |
      v
thin Odyssey runtime/adapter
      |
      v
odyssey_core.execute_request()
      |
      +--> Sol/low request planner
      +--> deterministic filters + current whole-note MiniLM retrieval
      +--> existing contextual resolution
      +--> existing Luna-backed semantic write/fact-selection boundaries when required
      +--> deterministic CREATE / safe UPDATE / DELETE / migration / bulk behavior
      +--> Markdown source of truth
      +--> durable pending work when needed
      `--> request-correlated local Git history
      |
      v
refresh derived indexes after successful knowledge mutation
      |
      v
subsequent request can retrieve the new knowledge
```

## What “connect everything” means in Phase 18

Phase 18 wires **everything already adopted as production behavior**. It does not automatically promote benchmark-only components into production.

### Included

- `odyssey_core.application.execute_request()` as the application composition boundary;
- the current `gpt-5.6-sol` / low top-level planner;
- deterministic filters and the current whole-note `ContextIndex` / MiniLM retrieval path;
- the existing semantic write-target and contextual-resolution boundaries;
- the selected `gpt-5.6-luna` / medium bounded writer where the existing UPDATE contract requires semantic body reconciliation;
- the existing Luna semantic fact-selection boundary where the approved fact correction/removal contract requires it;
- deterministic CREATE and other already-adopted materializers;
- Markdown persistence, durable pending-work evidence, and request-correlated local Git history;
- an explicit derived-index refresh after successful Markdown mutation so the next request can observe the change;
- one thin n8n-facing runtime/transport adapter that does not move domain logic out of Core.

### Explicitly not activated by Phase 18

The following remain evidence or deferred hypotheses and **must not be enabled merely because their benchmark code exists**:

- Combined entity+fact retrieval;
- a fixed production `Top-500` fact candidate contract;
- the Phase 17E Luna `SELECT | ESCALATE` retrieval reducer;
- the Phase 17E benchmark Sol answer-path as an implicit production retrieval policy;
- query-decomposed multi-fact retrieval;
- the future Luna first-pass `PLAN | ESCALATE -> Sol` cost-routing experiment.

Production retrieval therefore remains the current whole-note path unless the real E2E exposes a concrete blocker.

## Smallest real E2E

Use a disposable E2E vault, not the user's real personal vault, for the first proof.

### E2E A — write

Example request:

```text
Marta trabaja en Thales y vive en Lyon.
```

The evidence should show:

```text
n8n request
   -> Sol/low RequestPlan
   -> safe CREATE/UPDATE decision
   -> canonical Markdown mutation
   -> request_id-correlated Git history
   -> derived-index refresh
   -> typed result returned to n8n
```

The test must inspect the resulting Markdown and derived index state rather than treating an HTTP 200 as proof of success.

### E2E B — read back the newly written knowledge

Example request:

```text
¿Dónde trabaja Marta?
```

The request must pass through the same n8n/runtime/Core boundary and the **current production retrieval path** must recover the newly written note after index refresh.

The first read proof may expose the grounded `ContextPackage` directly. A user-facing natural-language answer may then be added as a thin bounded answer boundary in Phase 18 once the transport/retrieval proof is green. If that introduces or changes a production model-facing prompt or structured-output contract, `AGENTS.md` requires focused live evidence plus proportional regression sentinels before it is considered validated.

This sequencing prevents an answer-rendering issue from hiding a more fundamental integration/index-refresh failure.

## Runtime / transport boundary

Do not make a server a semantic dependency of Odyssey Core.

Conceptually:

```text
                 Odyssey Core
                /            \
               /              \
 Raspberry adapter          future mobile/client adapter
        |                           |
       n8n                         app
```

The Raspberry environment selected the smallest reliable local transport: a tiny long-lived host HTTP adapter. It avoids repeatedly loading local embedding/model resources while keeping n8n decoupled from the Python environment. A one-shot CLI/process boundary is no longer an open option for this phase.

Whichever transport is selected:

- it must be a thin adapter around existing Core boundaries;
- it must not duplicate planning, retrieval, persistence, or authorization logic in n8n;
- it must not make HTTP/server deployment mandatory for future Core use;
- it must expose a small stable request/result contract suitable for later clients.

### Phase 18.1 runtime decision

The Raspberry environment resolves the local transport as a persistent host-side HTTP adapter.
n8n runs in Docker without Python or the Odyssey checkout mounted, while the host .venv already
contains OpenAI, FastEmbed, SQLite, and the Core package. The container can reach the Docker host
gateway (172.18.0.1), so a host process avoids both a new Docker service and repeated MiniLM
startup. The adapter defaults to loopback; deployment binds it to the Docker bridge interface and
sets ODYSSEY_RUNTIME_URL for the development workflow.

    n8n HTTP Request node
            |
            | POST /execute {"request": "..."}
            v
    persistent host odyssey_runtime process
            |
            v
    odyssey_core.execute_request()
            |
            +--> host .venv: Sol/low and existing Luna boundaries
            +--> /data/odyssey/vault: authoritative Markdown
            +--> /data/odyssey/runtime: MiniLM-derived SQLite indexes
            +--> /data/odyssey/runtime/phase11a-benchmark/embedding-cache: FastEmbed model cache
            +--> /data/odyssey/state/pending: durable incomplete-work records

The composition root is odyssey_runtime.composition. It reads paths, actor, timezone, and port
configuration from the environment, constructs the existing Core adapters once at process startup,
and calls execute_request() for each request. After a result with affected note IDs, it rebuilds
the derived context and semantic indexes from Markdown. odyssey_runtime.serialization exposes
only bounded application evidence: request ID, status, action/retrieval evidence, affected IDs,
pending-work status, and Git history. It never returns prompts, provider payloads, raw exceptions,
or hidden model reasoning.

The development workflow source is workflows/odyssey-runtime.ts. It accepts one workflow input
named request and delegates to the adapter with an HTTP Request node. The adapter is a process
boundary, not a Core dependency; a future local or mobile caller can compose the same Core
contract directly.

For the Raspberry deployment, the process lifecycle is intentionally foreground-oriented so an
existing supervisor can restart it without Core changes. The deployment supplies
ODYSSEY_RUNTIME_HOST=172.18.0.1, ODYSSEY_RUNTIME_PORT=8765, and
ODYSSEY_RUNTIME_URL=http://172.18.0.1:8765/execute through its environment, then starts
/home/ragdehl/projects/odyssey/.venv/bin/python -m odyssey_runtime. No credential or secret is
stored in the repository. Process supervision, restart policy, and final workflow activation remain
part of the 18.2 deployment/E2E step.

Phase 18.1 does not activate Combined retrieval, Top-500 retrieval, Luna retrieval reduction,
query decomposition, Luna-first planning, MCP, authentication, or any new Docker service.
Installation and lifecycle supervision of the host process are deployment work for the real E2E,
not hidden side effects of Core. Phase 18.1 is complete; the Phase 18.2 write checkpoint remains
incomplete until provider access is restored.

## Index freshness

Markdown remains authoritative. SQLite/embedding indexes remain derived and rebuildable.

Phase 18 must make freshness explicit:

```text
successful knowledge write
        |
        v
Markdown is authoritative
        |
        v
refresh/rebuild affected derived state
        |
        v
next request sees the new knowledge
```

The initial E2E may use the simplest safe rebuild/refresh mechanism already supported by the indexes. Incremental optimization is out of scope unless measurement proves the full refresh is a blocker.

## Phase 18.2 write checkpoint evidence

The first real WRITE attempt was run on 2026-09-02 against a disposable workspace only:

```text
/data/odyssey/e2e/phase18/20260902T211826Z-phase18-write/
    vault/      local Git repository, initially empty
    runtime/    derived context.sqlite3 and semantic.sqlite3
    pending/    durable pending-work root
```

The host runtime used the repository schema, the existing read-only FastEmbed cache,
`TZ=Europe/Paris`, actor `phase18-e2e`, and Docker bridge address `172.18.0.1:8765`. n8n
execution `104` entered the development workflow `Odyssey — runtime bridge (Phase 18 E2E)` and
successfully reached the HTTP adapter. The requested input was exactly:

```text
Marta trabaja en Thales y vive en Lyon.
```

The adapter returned request ID `2311178f-875c-40b3-8b04-9366294a0def`, with application status
`failed` and bounded error `Request planner provider call failed`. A bounded provider diagnostic
confirmed HTTP 429 `credit_balance_exhausted` from `gpt-5.6-sol` with reasoning `low`. No validated
RequestPlan was available, so no Core mutation was attempted: the disposable vault has no Markdown
notes, no Git commit or request trailer, no pending work, and the two derived SQLite databases
contain no written knowledge. Luna was not called because Sol planning failed first. Provider cost
and token usage are unavailable for this failed/quota-rejected request.

This is an environment/provider-quota failure at the planner boundary, not evidence of semantic
write correctness. The run stopped before Phase 18.3, and no request was sent to the real personal
vault at `/data/odyssey/vault`.

## Acceptance criteria

Phase 18 is complete when observable evidence proves all of the following:

1. a real request enters through an n8n workflow;
2. n8n delegates domain execution to a thin Odyssey adapter rather than reimplementing Core logic;
3. the request reaches `execute_request()` using the real adopted model/provider boundaries for the E2E environment;
4. one write request produces the expected canonical Markdown result in a disposable E2E vault;
5. the same `request_id` is visible in the application result and request-level Git history where history is enabled;
6. incomplete work, if deliberately exercised, remains typed and durable rather than disappearing;
7. successful knowledge mutation refreshes/rebuilds the derived indexes required by subsequent retrieval;
8. a second request through n8n retrieves the knowledge created by the first request using the current whole-note retrieval path;
9. deterministic tests cover adapter/runtime serialization, failure behavior, and index-refresh orchestration without live API calls;
10. one bounded real E2E run on the Raspberry records enough evidence to inspect request, plan/result, Markdown, index state, and Git result without exposing secrets or hidden model reasoning;
11. the full repository verification and server-side CI remain green.

If a user-facing Sol answer boundary is added before Phase 18 closes, it must be grounded only in supplied retrieval evidence, fail safely on insufficient evidence, and have the focused live evidence required by `AGENTS.md`.

## Out of scope

- adopting Combined or a fixed Top-500 production retrieval policy;
- query decomposition / entity evidence aggregation;
- broad retrieval tuning or another synthetic strategy search;
- Luna first-pass planner cost routing;
- users, groups, permissions, sharing, sync, or conflict resolution;
- Android/iOS application implementation;
- MCP/public SDK/plugin framework;
- remote backup/push/pull automation;
- production-grade observability platform;
- performance optimization without a measured E2E bottleneck.

## Open decisions

1. **Local transport:** **resolved in Phase 18.1** as the persistent host HTTP adapter; do not reopen this decision.
2. **Read response surface:** first prove grounded retrieval end-to-end; then decide whether the same Phase 18 closes with a thin user-facing Sol answer adapter or whether that is split into the final Phase 18 substep.
3. **Index refresh granularity:** use the simplest safe existing rebuild first; optimize incrementally only if real measurements justify it.

No retrieval-strategy decision is open in Phase 18: current whole-note retrieval remains authoritative for this phase.

## Suggested implementation sequence

```text
18.0  contract + architecture challenge                         ✅ documented here
18.1  runtime dependency assembly + thin local adapter          ✅
18.2  n8n -> Core real WRITE E2E                               current / blocked by provider quota
18.3  post-write index freshness + n8n -> Core READ E2E         ⬜
18.4  grounded user-facing answer surface, if kept in Phase 18  ⬜
18.5  final evidence / deterministic verification / PR review   ⬜
```

## Architecture challenge

Result: **PROCEED**.

The real problem is not missing domain behavior; Phase 17A–17E already provide the relevant Core boundaries and evidence. The missing capability is a reliable external composition path and proof that the authoritative Markdown write lifecycle and rebuildable retrieval state remain coherent across consecutive real requests.

The simplest architecture is therefore a thin n8n-facing adapter around `execute_request()`, plus explicit index freshness. n8n continues to own triggers/integrations; Core continues to own knowledge semantics. Experimental retrieval reduction remains excluded until post-E2E evidence justifies revisiting it.

The only implementation-sensitive choice is the local transport. That choice can be made from the Raspberry environment without changing the approved product architecture and without making a server mandatory for future clients.

Human decision required: **NO**.
