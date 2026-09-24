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
and each model's configured maximum output tokens. Its actual hard exposure is all ten possible
Luna attempts plus at most one Sol fallback: **$0.455998 for at most 11 calls**. This remains
within the one-run $0.46 authorization used on 2026-09-24 at
`2405b136fc9abe686efb49599ba6368e479fe71a`. That one command passed frozen preflight, reserved
its exclusive evidence path, then stopped during Luna planner construction because
`OPENAI_API_KEY` was unavailable. The reserved JSONL is zero bytes with zero rows: **zero provider
calls, zero attempted cases, zero fallback, no usage, and no calculable actual cost**. This is not a
semantic pass; the focused gate remains blocked on provider credentials and a separately authorized
future execution. The one executed command was:

```bash
python -m benchmarks.reference_relationship_v1.run_live --confirm-live-provider-calls
```

The deterministic evaluator and cost guard are covered under
`tests/benchmarks/test_reference_relationship_v1.py`. The reserved evidence file must not be
overwritten or deleted to create a rerun.
