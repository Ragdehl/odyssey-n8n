# Phase 15.1 schema-aware write-planning benchmark

This is separate evidence for the refined `target + properties` contract. It deliberately does not
modify any historical Phase 15 artifact. The frozen input set has fifteen single-call Sol/low cases:
the twelve property/schema cases required by the contract and three Phase 15 regression sentinels.

Every case fixes `current_context` to `2026-08-22 09:30 Europe/Paris`; P07 therefore has the
reproducible expected domain date `2026-08-20`. `schema_snapshot.json` locks the canonical schema
digest and defines the synthetic `car.registration_number` extension. The runner rejects canonical
schema drift before calls and persists the complete effective synthetic schema per result.

The runner constructs `input`, the system prompt, and strict Structured Outputs schema by calling the
production `render_request_planner_prompt` and `request_plan_json_schema` functions, with the exact
production response format name (`odyssey_request_plan`), model, low reasoning effort, and
`store=false`. Each raw row contains the complete API input, effective schema, provider output,
parsed/validated output, oracle result, usage, and any provider or validation error. Rows are fsynced
immediately after each call. There is intentionally no retry option. An explicit `--case-id` is only
for a documented minimal follow-up after a production correction; it creates separate evidence and
never overwrites or retries the original result.

The oracle is narrow: it reports `INVALID` for local contract rejection, `FAIL` for an explicit
required semantic invariant, and `PASS` otherwise. It does not use an evaluator LLM or treat
alternate harmless wording as a failure.

## Execution record — 2026-08-22

The complete run `phase15-1-sol-low-20260822-network` made 15 Sol/low calls: **13 PASS, 1 FAIL,
1 INVALID**. P09 incorrectly inferred `journal_entry` from a transient reflection mentioning
“hoy”; the production prompt was tightened, the change received a deterministic test, and the
one-case follow-up passed. P05 initially emitted an empty action list and, after the Structured
Outputs `actions.minItems=1` correction, emitted an `amend` with neither fact nor property. Both
are correctly `INVALID` locally: the input identifies a target but supplies no requested mutation.
Treat it as an incomplete request/contract boundary, not a safe no-op or permission to invent a
relationship.

The explicit follow-up `phase15-1-sol-low-20260822-followup` made two further calls: P09 **PASS**;
P05 **INVALID**. The sandbox-only attempt `phase15-1-sol-low-20260822` is preserved separately:
all 15 requests ended in `Connection error`, consumed zero reported tokens, and is harness/network
evidence rather than model-quality evidence. The 17 network-reachable calls reported 100,802 input,
82,347 cached input, 18,404 cache-write, 2,379 output, and 1,044 reasoning tokens; using the frozen
pricing snapshot, their estimated total is **$0.227823 USD**.

Consequently the Phase 15.1 benchmark is not accepted and this PR remains a Draft pending a human
decision on the mutation-less P05 request shape or a revised complete semantic input. Raw, parsed,
validated, usage, prompt/schema, and oracle evidence are append-only under `results/`.

Run once only after deterministic tests pass:

```bash
python -m benchmarks.phase15_1_schema_write_planning.run_benchmark phase15-1-sol-low-YYYYMMDD
```
