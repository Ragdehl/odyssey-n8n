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
on the first failed or fail-closed classification and has no automatic rerun.

The no-cache ceiling counts the inherited production prompts, both Structured Outputs schemas,
and each model's configured maximum output tokens, allowing all ten logical cases to take both
provider attempts. With the current frozen registry it is **$3.590590 for at most 20 calls**,
above the authorized $0.15 ceiling. Therefore the one authorized gate was refused before
provider construction; there are no live case results or fallback counts. This is a cost gate,
not a semantic pass. The exact refused command was:

```bash
python -m benchmarks.reference_relationship_v1.run_live --confirm-live-provider-calls
```

The deterministic evaluator and cost guard are covered under
`tests/benchmarks/test_reference_relationship_v1.py`. A later live run needs a separately
authorized ceiling or a reviewed smaller gate whose full fallback exposure fits its limit.
