# Phase 17A executable application flow

Status: **contract approved; implementation pending**

This document is the canonical contract for Phase 17A. It intentionally narrows the earlier broad Phase 17 direction into a small executable Core application boundary first, while preserving later Phase 17 work explicitly so it is not forgotten.

## Objective

Compose the already-validated Odyssey planning, resolution, reference-preflight, retrieval, and materialization primitives into one small Core application flow that can execute one logical user request and return a stable typed result.

```text
raw user request
      |
      v
Sol/low planner
      |
      v
validated RequestPlan
      |
      v
Phase 17A application executor
      |
      +--> retrieve
      +--> single CREATE / UPDATE / DELETE / type migration
      +--> deterministic bulk UPDATE
      +--> cross-unit reference dependencies
      `--> typed deferred / unsupported result where execution cannot continue safely
```

This is a composition boundary, not a generic workflow engine.

## Request identity

Phase 17A introduces a stable `request_id` at the application boundary.

The `request_id` identifies one logical Odyssey request and is propagated through the application result and execution evidence. It is generated once per request, preferably as a full UUID, and must not be regenerated per action or per note.

The request ID is intentionally useful beyond 17A:

```text
request_id
   |
   +--> 17A application result
   +--> 17B durable pending work
   +--> 17C Git commit metadata / trailer
   +--> future request-history records
   `--> future operational tracing correlation
```

Phase 17A does not yet require persistent request-history storage or a tracing backend. The important architectural decision is that later capabilities reuse this existing stable correlation key rather than inventing incompatible IDs.

## Application boundary

Prefer the smallest explicit Core API, conceptually similar to:

```python
execute_request(
    user_request: str,
    *,
    planner,
    repository,
    schema,
    semantic_index,
    embedder,
    contextual_reasoner,
    writer,
    ...
) -> ApplicationResult
```

Exact public names remain an implementation detail, but the boundary must:

1. create one `request_id`;
2. obtain one validated `RequestPlan` through the existing planner boundary;
3. execute actions in planner order;
4. reuse existing Core primitives rather than reimplementing them;
5. collect typed per-action/per-unit evidence;
6. return one stable `ApplicationResult` containing `request_id`, overall status, ordered action results, affected stable IDs, and deferred/unsupported work evidence.

Do not create a generic DAG/workflow abstraction unless implementation evidence proves one is necessary.

## Action execution

### RetrieveAction

Reuse the existing validated retrieval/context machinery. The application executor coordinates it; it does not reinterpret the query semantically.

### WriteAction

For ordinary single-cardinality writes:

1. preflight all ordered units once through the existing target/reference preflight boundary;
2. preserve the returned target decisions and preallocated CREATE identities;
3. bind only safe references using existing Phase 16.5 behavior;
4. execute materialization through the existing CREATE, UPDATE, DELETE, and type-migration functions;
5. never independently resolve the same unit again after preflight merely because another unit references it.

### Bulk UPDATE

Reuse the existing deterministic `all_matching` selection and per-note update path. Partial successes remain successes and failures remain explicit per-note evidence.

### DelegateAction

Phase 17A does not build app routing or specialized external execution. Preserve a typed delegated/deferred application result containing the validated delegated request and optional selection criteria. Phase 18 or later may route it to n8n or a specialized capability.

## Cross-unit dependencies

Phase 17A owns execution ordering between units of the same WriteAction where one unit references another.

A dependent mutation must never be authorized by guessing a missing/ambiguous dependency.

Conceptually:

```text
preflight every unit
      |
      +--> safe existing or authorized CREATE target
      |
      `--> ambiguous / unresolved

safe dependencies
      -> execute in an order that preserves valid bound links

unsafe dependency
      -> preserve typed deferred evidence
      -> do not create an invalid wikilink
      -> do not reinterpret identity later
```

When an independent unit can safely succeed despite another independent unit failing, it may remain successful. Phase 17A does not introduce global rollback.

The initial executor may keep deferred work only in its returned result. Durable persistence of that work belongs to Phase 17B.

## Stable application result

The result must be suitable for a future n8n/API boundary without exposing low-level implementation details.

At minimum it should preserve:

- `request_id`;
- overall status such as completed / partial / needs_attention / failed;
- ordered action results;
- affected stable note IDs and operation type where useful;
- per-note results for bulk updates;
- candidate IDs/reasons for ambiguity or clarification;
- delegated/deferred work evidence;
- enough information for Phase 17B to persist pending work later without reconstructing the original planner intent.

Do not include hidden model reasoning or chain-of-thought.

## Failure and partial-success semantics

- Validation or planning failure before mutation: zero writes.
- A dependent unit whose prerequisite cannot be safely bound: do not execute that dependent mutation.
- Independent valid units may succeed even when another independent unit fails.
- Successful writes are not rolled back merely because another unit fails.
- The result must make partial success explicit.
- Per-note materializers retain their existing revision/schema/identity guards.

## Deterministic testing policy for model-backed boundaries

Phase 17A tests validate application composition, not whether already-evidenced production models happen to return the same output again.

Ordinary automated tests and CI **must not call live model APIs**. Inject deterministic fakes, mocks, or stubs for model-backed boundaries such as:

- the Sol request planner;
- the contextual resolver/reasoner;
- the Luna semantic UPDATE writer;
- any later model-backed or external adapter used by the application boundary.

Tests may supply already-validated `RequestPlan` values or controlled fake model outputs and should assert deterministic behavior including:

- action and dependency ordering;
- calls made and calls deliberately not made;
- partial-success semantics;
- affected stable IDs and persistence outcomes;
- ambiguity/deferred evidence;
- `request_id` propagation;
- failure handling without accidental writes.

The normal pytest/CI suite must run without OpenAI credentials, without network access, without spending model tokens, and without depending on model variability.

No new live Sol/Luna benchmark is required merely because Phase 17A composes existing boundaries. If implementation materially changes a production model prompt, model-facing instruction, Structured Outputs schema, or semantic writer contract, follow `AGENTS.md` and run focused live evidence only for the changed contract plus proportional historical sentinels. Do not use live calls simply to prove orchestration code works.

## Acceptance criteria

Phase 17A is complete when deterministic tests prove that one application call can compose the existing primitives for representative requests including:

1. read-only retrieval;
2. one existing-note UPDATE;
3. one CREATE;
4. DELETE;
5. type migration;
6. deterministic bulk UPDATE with per-note evidence;
7. multi-unit CREATE/reference dependency using preallocated identities and valid wikilinks;
8. ambiguous/unresolved dependency producing typed deferred evidence without invalid writes;
9. partial success across independent units;
10. DelegateAction represented safely without pretending it was executed;
11. one stable `request_id` propagated across the complete application result;
12. no duplicate target resolution for reference occurrences after action preflight.

The full existing deterministic suite must remain green.

No new live LLM benchmark is required merely for composition if the production Sol planner prompt/Structured Outputs contract and Luna writer contract remain unchanged. If implementation materially changes either production model contract, follow `AGENTS.md` and add focused live evidence.

## Out of scope for 17A

- durable pending-work Markdown artifacts;
- Git commits or history integration;
- automatic push/pull or remote backup;
- `user_request` as a canonical note type;
- semantic request-history retrieval;
- a tracing backend or observability platform;
- n8n orchestration;
- specialized DelegateAction routing;
- generic transaction/rollback machinery;
- generic DAG/workflow engine;
- UI/HITL.

## Preserved next work — do not forget

### Phase 17B — durable pending work

Persist unresolved dependencies, ambiguous references, failed/deferred targets, and other actionable incomplete work in a small inspectable internal Markdown boundary. It must preserve the original `request_id`, normalized action/unit evidence, candidate/affected stable IDs, failure reason, and enough context to retry or resolve later. Pending work is workflow/application state, not ordinary indexed user knowledge.

Future HITL should operate on this durable pending work rather than reconstructing ambiguity from scratch.

### Phase 17C — local Git history per logical request

Add the smallest Git adapter around the authoritative Markdown vault. Per-note materializers remain unaware of Git. Prefer one local Git commit containing successful Markdown mutations for one logical request and correlate it through:

```text
Odyssey-Request: <request_id>
```

Git remains audit/history/recovery infrastructure, never source of truth. Partial-success requests commit the successful independent changes and preserve failures through 17B. Automatic remote push/pull, backup-provider selection, and multi-device conflict handling remain later operational decisions.

### Future semantic request history

The previous direction proposed a canonical `type=user_request`. Do **not** add that type during 17A. Doing so would force ordinary resolution, retrieval, bulk selection, CREATE, and planner projections to carry an internal-type exception before real end-to-end evidence proves it valuable.

The product goal remains preserved: later Odyssey should be able to answer questions such as “what did I ask yesterday?” or “what changed when I told you Marta moved?”. After the first real E2E flow exists, reassess the simplest internal request-history representation. It may reuse Markdown, but it need not be an ordinary canonical knowledge type.

Any future request-history record should correlate through the existing `request_id`, preserve the raw user request, validated RequestPlan, execution outcome, and affected IDs, and never store hidden chain-of-thought. Do not embed the same Git commit SHA inside a record committed by that commit; correlate through `request_id` instead.

### Future tracing

Do not build full tracing in 17A. Preserve the direction:

- propagate `request_id` now;
- later introduce a separate `trace_id` only if a request can contain multiple operational traces/retries and that distinction proves useful;
- wrap LLM/persistence/external boundaries rather than adding manual logging to every domain function;
- keep operational traces separate from semantic knowledge and request history;
- never store hidden model reasoning.

The natural implementation point is Phase 18/19, once n8n and the first real E2E request expose the actual operational boundaries worth tracing.

## Architecture challenge

Result: **PROCEED with the revised split**.

The original Phase 17 direction grouped application execution, durable workflow state, Git history, semantic request history, and tracing into one phase. That coupling was unnecessary before Odyssey could execute one complete request. The revised sequence keeps the same product goals while minimizing accidental complexity:

```text
17A  executable Core application flow + request_id
17B  durable pending work
17C  local Git history per request_id
18   n8n integration + first real E2E
19   hardening / tracing / evidence-driven request-history refinements
```

Human decision required: **NO**. The user approved this revised phase decomposition and the `request_id` direction before implementation.
