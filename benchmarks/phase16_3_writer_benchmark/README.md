# Phase 16.3 bounded writer benchmark

This directory contains frozen synthetic evidence for issue #38. It is not production writer
integration and it does not read or write the personal vault.

The benchmark evolved deliberately from a cost-first Luna/low trial into the final selected policy:

```text
Luna / low full-note baseline
        |
        +--> long-note supplement exposes one dangerous semantic miss (L03)
        |
        +--> real MiniLM Top-3/Top-5 context filtering drops required evidence
        |
        `--> Luna / medium + full authoritative note
                      |
                      `--> 15/15 difficult cases PASS
```

The selected Phase 16 writer policy is therefore:

```text
full authoritative note
        |
        v
gpt-5.6-luna / medium
        |
        v
bounded operation
        |
        v
Core exact-span / revision / schema validation
```

Do not add MiniLM/NLI within-note writer filtering, low/medium routing, or Terra/Sol writer fallback
in the initial implementation. Exact normalized duplicate shortcuts plus canonical structured
properties/tags remain deterministic.

Historical raw provider evidence remains append-only under `results/`. The Luna-medium final
comparison is in `results/phase16-3-luna-medium-20260825/`; its raw provider records remain in
`raw_results.jsonl` and the explicit human semantic adjudication is in `adjudication.json`.

The original frozen corpus contains 60 cases (45 existing-note mutations and 15 `CREATE_BODY`
cases), with separate long-note, oracle-reduced, real-MiniLM-retrieval, and Luna-medium follow-up
evidence retained to show how the final architecture was selected.

The evaluator validates the strict output shape, exact current-body spans, operation families,
single-operation `NO_CHANGE`, metadata/link leakage, and oversized anchors. Semantic faithfulness
still requires explicit adjudication; deterministic checks are not treated as a substitute for
natural-language review.

No Terra or Sol writer calls were required for the final selection. Human review accepted
`USE_LUNA_MEDIUM_FULL_NOTE`; production materialization is the next Phase 16 step.
