# Reference & Relationship Resolution v1 — Slice 3 focused gate

This frozen gate uses the production `LunaFirstRequestPlanner.from_environment` composition:
Luna `gpt-5.6-luna` / low, followed only after local invalidity by at most one Sol
`gpt-5.6-sol` / low fallback. Safe Luna escalation becomes clarification. It never executes
retrieval or mutation.

`cases.json` contains five relational cases and five exposed-semantics sentinels.
`oracle.json` evaluates action, source/reference wording, cardinality, fact and reference shape;
it does not require exact prose. `manifest.json` freezes the registry, evaluator, and the
2026-09-23 pricing snapshot. The runner retains only validated results and bounded provider
attempt metadata in an exclusive, gitignored JSONL output, flushing after each case. It stops
on the first failed or fail-closed classification **or the first Sol fallback**, and has no
automatic rerun. The fallback row is retained before that stop so it can be reviewed.

The no-cache ceiling counts the inherited production prompts, both Structured Outputs schemas,
and each model's configured maximum output tokens. After adding the complete-set teaching example,
the current branch's hard exposure is all ten possible Luna attempts plus at most one Sol fallback:
**$0.458174 for at most 11 calls** (42,655 Luna input tokens and 66,592 Sol input tokens at the
conservative bounds). This remains within the existing $0.46 guard. The next possible run has its
own exclusive `reference-relationship-v1-attempt-3.jsonl` target. Attempt 1 at
`2405b136fc9abe686efb49599ba6368e479fe71a` passed frozen preflight, reserved its exclusive path,
then stopped during Luna planner construction because `OPENAI_API_KEY` was unavailable. Its retained
`reference-relationship-v1.jsonl` is zero bytes with zero rows: **zero provider calls, zero attempted
cases, zero fallback, no usage, and no calculable actual cost**.

Attempt 2 at `e17b5f750573e39aebf8477e933902e083ad7f9f` used the distinct exclusive
`reference-relationship-v1-attempt-2.jsonl` path after the operator loaded the protected source into
the child-process environment. It made three Luna-only calls: R01 and W01 passed; W02 returned the
safe `UNRECOGNIZED_REQUEST` clarification and therefore failed closed as `unexpected_clarification`.
The runner flushed that third row and stopped: **3 attempted cases, 3 Luna calls, 0 Sol calls, 0
fallbacks, 2 PASS, 1 FAIL_CLOSED, and no semantic-review flags**. Actual Luna usage was 23,076 input
tokens (15,352 cached), 548 output tokens, and 275 reasoning tokens over 11,432.727 ms. The frozen
pricing snapshot calculates **$0.00250944** actual cost. The focused gate did not pass; no retry or
additional provider call was made. The executed command was:

```bash
python -m benchmarks.reference_relationship_v1.run_live --confirm-live-provider-calls
```

The deterministic evaluator and cost guard are covered under
`tests/benchmarks/test_reference_relationship_v1.py`. The runner now refuses a missing
process-exported `OPENAI_API_KEY` before reserving evidence or constructing a provider. Neither
attempt artifact may be overwritten or deleted to create a rerun.

The post-Attempt-2 follow-up adds one non-evaluation Luna teaching example for this exact
complete-set source-write shape, using different English dinner/company wording rather than the W02
sentence. It leaves cases, oracle, evaluator, Core, and fallback behavior unchanged. **No new live
evidence has been run**; a fresh separately authorized attempt is required to evaluate the lesson.
