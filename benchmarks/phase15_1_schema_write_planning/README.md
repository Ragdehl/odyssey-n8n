# Phase 15.1 schema-aware write-planning benchmark

This is separate evidence for the refined `target + properties` contract. It deliberately does not
modify any historical Phase 15 artifact. Version 1.0 is retained in the original raw results and
the reviewed rows are indexed in `cases.v1.0.json` / `oracle.v1.0.json`. Version 1.1 is the
corrected follow-up case set; it has fifteen single-call Sol/low cases:
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

The v1 review changed adjudication, not historical rows: P09's original `journal_entry` output is
semantically acceptable and the old oracle was wrong; P05's original output remains invalid evidence
for the intended amend behavior because its input supplied no mutation. The production validation
still rejects empty `amend`/`remove` payloads. The special prompt rule added after v1 was removed;
type semantics remain schema-driven. R01–R03 now require their essential target and fact/query
content, not only action shape.

## Execution record — 2026-08-22

The historical run `phase15-1-sol-low-20260822-network` made 15 Sol/low calls: **13 PASS, 1 FAIL,
1 INVALID**. Its raw rows remain unchanged. Offline reevaluation under v1.1 changes only P09's
adjudication from FAIL to PASS; the original P05 row remains INVALID because its input was incomplete.

The explicit follow-up `phase15-1-sol-low-20260822-followup` made two further calls: P09 **PASS**;
P05 **INVALID**. The sandbox-only attempt `phase15-1-sol-low-20260822` is preserved separately:
all 15 requests ended in `Connection error`, consumed zero reported tokens, and is harness/network
evidence rather than model-quality evidence. The 17 network-reachable calls reported 100,802 input,
82,347 cached input, 18,404 cache-write, 2,379 output, and 1,044 reasoning tokens; using the frozen
pricing snapshot, their estimated total is **$0.227823 USD**.

The earlier v1.1 five-case attempt remains append-only transport evidence. After the oracle correction,
one effective Sol/low call was made for P05 using the final production prompt/schema, `store=false`,
and `max_retries=0`. It passed: `target.type=person`, query retained “amiga” and “Marta”, the
exact 1990 birth-date range was emitted in `target.filters`, `properties=[]`, and facts retained
“Lyon”; no `relationship_to_user` was invented. Usage was 5,903 input tokens (5,900 cache-write),
155 output tokens, 54 reasoning tokens; estimated cost was `$0.041540 USD`. A preceding local runner
construction error is retained separately with zero provider calls and does not count as an OpenAI
call. Phase 15.1 is accepted and PR #29 is ready for human review.

Run once only after deterministic tests pass:

```bash
python -m benchmarks.phase15_1_schema_write_planning.run_benchmark phase15-1-sol-low-YYYYMMDD
```
