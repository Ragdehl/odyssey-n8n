# Phase 16.3 bounded writer benchmark

This is frozen synthetic evidence for issue #38. It is not production writer integration and it
does not read or write the personal vault. The sixty cases comprise 45 existing-note mutations and
15 `CREATE_BODY` cases. Luna makes one full-note call per case, followed by a Luna-only reduced
context comparison on the twelve cases carrying `reduced_context`. Terra receives only Luna
`MATERIAL_FAIL` cases; Sol receives only remaining Terra `MATERIAL_FAIL` cases.

```text
Luna full benchmark ── human semantic review ── MATERIAL_FAIL only ──> Terra
       │                                                                  │
       └── 12 full/reduced context probes                                 └──> Sol only if needed
```

Run the first stage only after reviewing this frozen dataset, prompt, schema, pricing, and
evaluator:

```bash
python -m benchmarks.phase16_3_writer_benchmark.run_benchmark \
  --run-id phase16-3-luna-low-YYYYMMDD --stage luna
```

Raw model evidence is append-only in `raw_results.jsonl`. Before escalation, create an append-only
`review.jsonl` beside it with the original records plus `semantic_status` (`PASS`, `MINOR`, or
`MATERIAL_FAIL`) and human findings. The runner refuses Terra/Sol when the prior stage has no
material failures. Deterministic failures are recorded separately and are always material until a
harness defect is demonstrated.

The evaluator validates the strict output shape, exact current-body spans, operation families,
single-operation `NO_CHANGE`, metadata/link leakage, and oversized anchors. It deliberately does
not pretend that string checks can decide natural-language faithfulness: a reviewer determines the
semantic status without changing frozen inputs or expectations.
