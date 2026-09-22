# Performance / Latency / Cost P1 — measurement and decision contract

Status: **phase contract; no live baseline or optimization executed**. The [Functional Roadmap](functional-roadmap.md) owns current status and order.

## Objective and sequence

Answer where an end-to-end request spends time, which individual provider calls cost money, how often and why Luna falls back to Sol, how much input each call receives, and which measured contributor is the best first optimization. Provider time and Odyssey overhead must be distinguishable before choosing a change. No universal latency SLA is set before baseline evidence.

1. **P1A — observability completeness:** preserve existing bounded evidence, close only diagnosis-blocking gaps, and freeze the cases, environment, pricing snapshot, and report format.
2. **P1B — baseline and bottleneck diagnosis:** run the approved synthetic DEV cases and identify dominant latency, cost, fallback, and input-token contributors. Record unavailable values honestly.
3. **P1C — one optimization:** select exactly one primary target from P1B evidence. This contract does not authorize its implementation now.
4. **P1D — before/after verification:** rerun the same frozen cases and semantic oracles with enough repetitions to distinguish a change from provider variance, within a separately approved budget.

## Actual request paths and current evidence

```text
Chat browser -> n8n /request -> runtime /execute -> Core planner + actions + Git/pending
                                         |                 -> runtime index refresh/snapshot
                                         `-> n8n route -> optional Luna grounded answerer -> browser
Notes browser -> n8n /notes -> runtime /notes -> optional Sol intelligent-search planner
                                         `-> Notes query service -> browser
```

Chat's browser submission also persists a user turn before the product request and attempts assistant-turn persistence after rendering. Those conversation calls are outside the Core `total_duration_ms`. The runtime HTTP server handles independent reads concurrently, while `execute_product` serializes product executions; queue wait for that lock is currently outside the timed `RuntimeComposition.execute` span. A completed mutation may be replayed by `request_id`; baseline runs must distinguish a fresh execution from replay. Source: `odyssey_web/app.js`, `workflows/odyssey-online.ts`, `odyssey_runtime/server.py`, `odyssey_runtime/composition.py`.

`ApplicationResult.operational` already carries a monotonic runtime total, ordered `planner`, `action.retrieve` / `action.write` / `action.delegate`, `git`, `pending`, and `index_refresh` stages. Action stages include contextual-resolution, writer, and fact-selector provider calls where invoked. Runtime serialization retains safe provider diagnostics. Luna-first planning records separate `planner.luna` and `planner.sol_fallback` calls with model, reasoning, duration, usage when supplied, and outcome. The planner stage is a parent interval: its duration and nested call durations must never be summed as independent request time. `request_id` correlates Chat, conversation, result, and Git evidence; Notes has its own operation path. Sources: `odyssey_core/observability.py`, `odyssey_core/application.py`, `odyssey_core/cost_aware_planning.py`, `odyssey_runtime/serialization.py`.

The current n8n `request_detail` projection keeps the stage/call name, outcome, duration, model, reasoning, usage, and `error_category`; it drops runtime-serialized `validation_stage`, `validation_code`, `parse_status`, `provider_status`, and related safe planner metadata. The browser displays the total, stages, usage, and whole-request estimated cost, but not per-call reasoning, failure class, or estimated cost. The answerer record created in n8n has model/reasoning/usage but no duration or failure evidence. The Notes route returns Notes results without `request_detail`, operational timing, or intelligent-planner usage. Sources: `workflows/odyssey-online.ts`, `odyssey_web/client.js`, `odyssey_web/app.js`, `odyssey_runtime/composition.py`.

### Observability inventory and gaps

`A` = sufficient now; `B` = measured or serialized but poorly projected/aggregated; `C` = missing and needed for P1; `D` = optional after diagnosis. “Duration” refers to a measured wall interval, never inferred from token counts.

| Boundary | Class | Duration today | Usage / cost today | Failure / route evidence today | P1 gap |
| --- | --- | --- | --- | --- | --- |
| Chat Core/runtime total and coarse stages | A | Runtime total, planner, each action, Git, pending, index refresh | Nested Core provider usage; n8n request estimate | Stage outcomes; `request_id` | Preserve these as the baseline; do not instrument every function. |
| Luna → Sol planner | B | Both calls and parent planner | Per-call tokens when supplied; both included in whole-request estimate when complete | Separate call names/outcomes; Luna's safe structural diagnostics are absent from product projection | Carry bounded failure/validation classification through request detail; distinguish semantic escalation/clarification from structural failure. |
| Retrieval and write action internals | B | Each action total; nested resolver/writer/fact-selector call duration | Nested provider usage/cost computable | Action/unit status | First subtract nested provider intervals without double counting; if action residual dominates, add only coarse resolution versus canonical mutation timing. |
| Git, pending, index refresh | A | Named stage when executed; skipped/unavailable otherwise | No API cost | Stage status/error class | None for initial diagnosis. |
| n8n grounded answerer | C | No measured provider duration | Usage is captured; included in total estimate only when supplied | Completion record is currently synthesized; failed/invalid response is not classified in that record | Measure call interval and safe outcome; retain unavailable usage on failure. |
| Browser → n8n → runtime transport / runtime queue | C | Core total excludes queue, n8n, browser transport, and conversation writes | No direct API cost | n8n executions and request IDs exist, but no compact end-to-end boundary timing | Capture one client-observed product-call wall interval and one outer runtime/request or n8n interval; compute only valid residuals. Keep conversation persistence separate. |
| Intelligent Notes search | C | No operational envelope | Sol planner usage and estimated cost absent from Notes response | Bounded Notes error, no call diagnosis or Notes `request_id` | Add bounded Notes operation total and individual planner-call metadata through the existing Notes response path; include query service time only if needed to explain residual. |
| Prompt/context components | B/D | No duration needed | Per-call input tokens are supplied by provider when available; no component split | Prompt assembled from fixed instructions, schema-derived capabilities, structured-output schema, Luna examples, recent turns, request text | First compare total input tokens by call/case. Only if dominant, collect deterministic byte/character lengths for coarse rendered components; no content or tokenizer approximation as billed tokens. |
| Conversation/request correlation | A/C | Conversation calls have no product-stage duration | N/A | Same `request_id` in Chat and saved result; `conversation_id` is `main`. Notes has no product request ID. | Runner must tag fresh/replayed Chat results and report conversation timing separately. Sequential N1 rows can use runner case/run identity and n8n execution identity; add a Notes request ID only if that cannot correlate its call safely. |

P1A should first verify that these source contracts match one disposable DEV response and its n8n execution projection. The code inventory alone is not live evidence. If an entire response stage is malformed or omitted, fail closed and mark the affected metric unavailable rather than silently filtering it out in a P1 report. A browser timing by itself does not allocate time between network, n8n, and runtime queue; label the residual “unattributed outer path” until a second boundary measurement supports a split.

## Fallback and input-size diagnosis

For each planner attempt report `planner.luna` or `planner.sol_fallback`, model, reasoning, outcome, elapsed time, supplied input/output/cache/reasoning counters, estimated call cost or `unavailable`, and bounded failure category. Luna's current `RequestPlanningError` grouping is too broad to distinguish incomplete provider response, malformed JSON, local structural validation, and semantic fail-closed validation in the user-facing projection. P1A should reuse existing safe codes where available and add a small safe classification at the Luna boundary where absent; do not persist exception messages, prompts, raw responses, or hidden reasoning. A safe `ESCALATE` becomes clarification and is not Sol fallback. Count fallback rate by eligible fresh requests and by frozen case class, with numerator, denominator, and incremental Sol time/cost. Do not infer a general rate from seven distinct cases alone; repetitions or a later bounded sample are needed.

The planner prompt is not just user text: Sol renders fixed safety/semantic instructions, dynamic retrieval and writable schema capabilities, optional bounded recent conversation, and a strict output schema. Luna inherits that prompt and adds its first-pass rules and teaching examples, plus its own strict schema. Therefore the prior observed ~11–12k planner input tokens are a **hypothesis trigger**, not evidence of waste. First use provider-supplied per-call `input_tokens` and `cached_input_tokens`. If input size is a material cost/latency contributor, derive component byte/character lengths at render time for fixed instructions, capability projection, conversation context, request text, teaching examples, and structured-output schema. Such lengths are explanatory proxies; they must not be labelled token counts or stored with content. Avoid a new tokenizer or telemetry store for P1.

## Cost contract

Usage counters are provider observations when returned, while all dollar amounts are **estimates**, not billing facts. The n8n product workflow uses the dated snapshot at `benchmarks/phase20_answerer/pricing_snapshot.json` (currently `2026-09-07`) injected at workflow render time. It prices `input_tokens - cached_input_tokens` at ordinary input rate, cached input at cached rate, and output at output rate; reasoning tokens are already within output tokens. The current calculation requires valid input, cached-input, and output counters plus a known model rate, and rejects cache-write tokens other than zero. Missing usage or an unknown rate makes the whole request `unavailable`, never zero. Luna and Sol fallback calls are enumerated independently; contextual resolver, writer, fact selector, and the n8n answerer are included when their call records and required counters survive projection. No billed invoice reconciliation or billing API is in scope.

P1A should expose an additive per-call estimated-cost breakdown beside the existing request total, with the same pricing date/source/version identity and no parent-stage double count. A stage subtotal is derived from its child calls. If one chargeable call has missing usage, report that call's cost and the **complete** request total as `unavailable`; optionally show a clearly labelled known-call subtotal. Verify the deployed DEV pricing snapshot matches the frozen baseline snapshot before collecting evidence. Existing `OperationalStage.estimated_cost_usd` is present in the Core type but is not populated or projected today; do not assume it is an existing cost breakdown.

## Frozen representative baseline, before execution

Freeze a versioned case registry, schema/source commit, DEV environment, synthetic note fixture, relevant conversation history, pricing snapshot, semantic oracle, and request order before the first live run. Each repetition starts from an equivalent disposable DEV state with fresh request IDs; reset or recreate only the disposable fixture so repeat writes remain comparable. Exclude setup/index-build time from request latency and record it separately. Never mutate the real vault. Baseline labels below are examples to freeze as exact strings in P1A.

| ID | Case and synthetic setup | Required semantic outcome |
| --- | --- | --- |
| R1 | Simple READ: `¿Dónde trabaja Marta?`; Marta's synthetic note has a known employer. | Grounded answer from that note; no mutation. |
| R2 | Conversational READ: prior turn explicitly discusses synthetic Marta, then `¿Y dónde vive?`; canonical note has a known home location. | Resolve Marta via recent turn, answer from canonical note; no mutation. |
| W1 | Simple WRITE: `Guarda que Marta prefiere el té.` with unique Marta. | One authorized durable fact; no unrelated note change. |
| W2 | Multi-note WRITE: `Marta prefiere el té y Elena prefiere el café.` with unique people. | Both facts discoverable on the correct synthetic identities; no identity conflation. |
| W3 | Natural narrative WRITE: `Marta y Elena se reunieron en casa de Pablo; Marta llevó té y Elena preparó café.` with three unique synthetic people. | Preserve the explicit narrative facts and identity references within currently supported semantics; no unsupported relation inference. Freeze the exact safe oracle after a deterministic feasibility review. |
| C1 | Fail-closed clarification: `???` with the same synthetic fixture. | `UNRECOGNIZED_REQUEST`; no mutation. |
| N1 | Notes intelligent search: `Busca notas de personas que prefieren el té` over the disposable notes. | Planner-backed Notes results match the frozen supported search/filter semantics; no mutation. |

Do not use kinship references, plural participant/group resolution, backlink-enriched retrieval, or relational graph traversal as P1 oracles. If a suggested W3/N1 oracle exceeds current supported semantics, adjust the **frozen case before live execution** and record that decision; never score a safe fail-closed result as a performance failure caused by an unsupported future feature.

For every case collect client-observed product wall time, runtime/Notes total and named stage durations, each actual provider call's role/model/reasoning/duration/available usage/cost/outcome, Luna-only versus Luna→Sol route, safe failure class, semantic oracle result, mutation/no-mutation result, replay flag, and outer-path residual where mathematically valid. Include conversation-turn timing separately for R2 and any user-visible end-to-end view. Never add nested provider durations to their parent action/planner interval.

## Future live runner and evidence budget

No provider call is authorized by this document. A future baseline run requires explicit human confirmation and a hard initial ceiling of **USD 0.20 total**. Reuse the existing frozen-case/immutable JSONL runner pattern; run sequentially with zero automatic retries, fail-closed malformed-result handling, incremental persisted rows, exclusive creation/refusal to overwrite prior evidence, and a resumable run identity bound to the exact case/source/schema/pricing configuration. The runner must account for all calls in one request, including possible Sol fallback, resolver/writer/fact-selector and answerer calls. Before every request or provider call it must conservatively reserve the maximum remaining possible charge from input-size bounds, model rates and configured maximum output tokens; stop before a call that could exceed the remaining ceiling. Actual usage replaces the reserve after a call; absent usage consumes the conservative reserve and remains `unavailable` in the report. If the current n8n/runtime boundary cannot enforce that cap for every call, the runner must refuse live execution until P1A supplies an enforceable budget boundary. If USD 0.20 cannot cover all seven cases under the conservative bound, run an approved smaller pilot or seek a separately approved higher ceiling after evidence; never silently exceed the cap. No credentials are requested or accessed during contract work.

## Diagnosis report and optimization rule

Report each case/repetition with observed intervals and estimated charges; `—` means unavailable, not zero. Use actual stage names and mark residuals, for example:

```text
Case W2 / fresh request ID
Client product wall             [measured]
Runtime total                  [measured]
  planner                      [measured parent]
    planner.luna               [measured call]  [estimated call cost]
    planner.sol_fallback       [not_called or measured call]
  action.write                 [measured parent; nested resolver/writer calls]
  git                          [measured]
  pending                      [skipped or measured]
  index_refresh                [measured]
Outer path residual            [derived only from compatible intervals]
Request API cost               [estimated / unavailable; dated pricing basis]
Semantic outcome / mutation    [frozen oracle result]
```

For R1/R2 add `action.retrieve` and n8n `answerer`; for N1 use the Notes operation and its planner/query boundaries. Summaries should show per-case medians and spread, call counts and fallback frequency with denominators, total and call-level estimated cost, and missing-data counts. Never present a difference of overlapping intervals as exact n8n time. Distinguish provider call wall time from local validation around that call, and label suspected avoidable overhead as a hypothesis until a controlled comparison supports it.

**Optimize the dominant avoidable contributor first, provided the change does not weaken semantic quality or safety.** P1B must choose from measured fallback, fixed prompt/schema overhead, retrieval/resolution, writer/answerer provider time, index refresh, n8n/runtime/browser transport, or another demonstrated contributor. If provider time dominates but no safe Odyssey change is evident, record that conclusion rather than inventing a fast path. P1C is one primary target, with a separate review for any model/prompt change and the repository's live semantic-evidence gate. A fast path is only a later proposal if measurements show unnecessary normal-path overhead and an equivalent-safety alternative exists.

## Acceptance criteria

- **P1A:** nearly all meaningful request wall time belongs to named coarse, non-overlapping intervals or a clearly labelled outer residual; each actual provider call is distinguishable; model/reasoning/usage/duration are represented when supplied; Luna→Sol is explicit with safe cause category; missing usage stays unavailable; request and per-call estimates identify a dated pricing basis; Notes intelligent search and answerer evidence meet the same minimum diagnostic standard.
- **P1B:** representative frozen cases identify dominant latency and API-cost contributors, show fallback rate/cost with denominator, and give enough input-token evidence to decide whether prompt overhead merits change. Missing measurements cannot be interpreted as zero or a conclusion.
- **P1C:** exactly one primary optimization is chosen from P1B evidence; semantic and safety contracts remain unchanged unless separately approved.
- **P1D:** the same cases and oracles are compared before/after, with enough repetitions and reported spread to rule out one unusually fast provider response; spend stays within explicit approved ceilings; no semantic, mutation-safety, or fail-closed regression.

## Boundaries, open decisions, and architecture challenge

Out of scope: backlink-enriched/entity or relational retrieval, graph traversal, relation properties, kinship/group/participant reference resolution, clarification chips, multi-type/controlled-tag/negative Notes filters, semantic fact deduplication, readable AI note view, Daily/date navigation, schema management, Tasks/Calendar, PROD deployment, billing scraping, hidden retries, weaker validation, entity-safety bypasses, multiple ad-hoc planners, request-class fast paths, new services, vector/graph infrastructure, or a second knowledge/telemetry authority.

Open decisions for P1A: (1) choose the smallest compatible outer timing boundary after one disposable DEV projection inspection; (2) freeze W3/N1 oracles against the currently supported contract; (3) establish a cap-enforceable runner path or reduce the pilot. These are measurement/feasibility decisions, not permission to choose P1C in advance. Human confirmation is required only before the future live baseline and for any later material contract/budget change.

**Architecture challenge result: PROCEED for the bounded P1 contract and P1A design.** Existing `ApplicationResult.operational`, runtime serialization, n8n execution data, UI-1 request detail, pricing snapshot, and immutable benchmark-runner patterns solve most of the problem. The missing data is concentrated at the Luna diagnostic projection, n8n answerer, outer wall boundary, and separate Notes intelligent route. Add only those coarse observations, preferably through the existing response contract. Do not add a tracing database, token-accounting subsystem, or per-function timers. A small component-size proxy is worthwhile only after input-token evidence points there. Keep P1A–P1D one decision sequence, but review P1C as a separate evidence-selected implementation slice. The prior decision to defer fast paths remains valid until measurement changes the evidence.
