# P1B live baseline — 2026-09-23

Source/deployment: `96a4fe76d9920a5de46a48b15cfda3c2cd44c650`
Environment: isolated disposable DEV only (`/data/odyssey-dev`)
Pricing: P1 snapshot `2026-09-23`
Machine evidence: [p1b-live-20260923-run2.jsonl](p1b-live-20260923-run2.jsonl)

One sequential execution ran each frozen case with a fixture reset before every case. The runner
used fresh Chat request IDs, made no retry, and persisted each completed row before starting the
next case. The two separate preflight artifacts in this directory stopped before any provider
request: one exposed the `odyssey-dev restart` n8n coherence precondition and one corrected the
internal `N8N_ENDPOINT_WEBHOOK=api` route. They are not baseline cases or spend.

| Case | Semantic oracle | Runner n8n wall | Runtime product wall | Core wall / coverage | Observed estimate |
| --- | --- | ---: | ---: | ---: | ---: |
| R1 | PASS | 14.195 s | 12.062 s | 11.956 s / 75.2% | $0.0480030 |
| R2 | PASS | 15.160 s | 13.161 s | 13.085 s / 94.4% | $0.0489322 |
| W1 | PASS | 16.287 s | 16.164 s | 16.025 s / 95.2% | $0.0492724 |
| W2 | PASS | 14.324 s | 14.202 s | 14.073 s / 94.7% | $0.0500978 |
| W3 | **FAIL** — `partial`, expected completed | 20.163 s | 20.037 s | 19.904 s / 96.2% | $0.0566628 |
| C1 | PASS | 6.864 s | 6.730 s | 6.627 s / 88.8% | $0.0466526 |
| N1 | PASS | 7.879 s | 7.824 s | 7.106 s / 100.0% | $0.0481282 |

The seven product webhook walls total **94.871 s**. Fixture setup and index rebuild time total
119.456 s and is deliberately excluded from request timing. Total observed estimated API cost is
**$0.3477490**. It is observed usage priced under the dated P1 snapshot, not a billing invoice or
a maximum.

## Planner evidence

Every planner execution took the same route:

```text
planner
├── Luna / low — provider completed, local validation failed
│   └── PLANNER_RESULT_ENVELOPE / INVALID_FIELDS
├── fallback_decision — completed
└── Sol / low — valid plan/clarification completed
```

| Case | Luna duration, input → output | Sol duration, input → output | Planner wall |
| --- | --- | --- | ---: |
| R1 | 4.924 s, 11,873 → 104 | 4.038 s, 10,829 → 103 | 8.962 s |
| R2 | 6.038 s, 11,920 → 118 | 6.287 s, 10,875 → 139 | 12.325 s |
| W1 | 3.809 s, 11,878 → 134 | 5.685 s, 10,834 → 170 | 9.495 s |
| W2 | 4.851 s, 11,883 → 221 | 7.225 s, 10,839 → 205 | 12.077 s |
| W3 | 6.058 s, 11,894 → 292 | 9.209 s, 10,850 → 494 | 15.267 s |
| C1 | 2.821 s, 11,869 → 49 | 3.061 s, 10,825 → 46 | 5.882 s |
| N1 | 3.928 s, 11,877 → 134 | 3.160 s, 10,833 → 113 | 7.088 s |

Luna fallback frequency is **7/7**. Luna's failed attempts consumed 32.428 s and $0.0179012;
Sol fallbacks consumed 38.665 s and $0.3289400. Sol is 94.6% of observed baseline API cost.
Both model calls had zero reported cached input tokens. Provider duration accounts for virtually
all attempt time; input construction, parsing, validation, and fallback selection were each at
most a few milliseconds.

The provider-reported planner input was stable: Luna 11,869–11,920 and Sol 10,825–10,875 input
tokens. The safe component-size proxies show why it is large: 11,263 bytes fixed instructions,
9,838 retrieval-capability bytes, 2,142 write-capability bytes, and about 35.6–35.8 KiB structured
output schema; Luna adds 4,103 bytes of rules/examples. R2 added only 181 recent-context bytes.
These are bytes, not billed-token allocations. This single pass establishes payload size and a
fallback correlation, but does not prove that prompt size causes the observed provider latency.

## Other measured work and limits

- R1/R2 retrieval was 21.4/19.2 ms, including one separately recorded local query embedding.
  The answerer added 1.950/1.789 s and $0.0002542 combined.
- W1 materialization took 3.319 s inside `unit[0].materialize`, but has no smaller meaningful
  child evidence. W2 materialized two units in 29.8/31.7 ms. This is a measurement gap, not a
  performance conclusion.
- W3 executed `contextual_resolution` once (2.051 s, 2,734 → 89 Luna tokens, $0.0006536), then
  had a 2.080 s `preflight.unit[3].target` interval and ended `partial`; its write semantic oracle
  failed. It was not rerun.
- Index refresh took 2.380 s (W1), 1.131 s (W2), and 1.140 s (W3). Git took 0.004–0.538 s.
- C1 is correctly fail-closed, but root coverage is 88.8%; R1 root coverage is 75.2%. Their
  residuals (744 ms and 2,969 ms) must remain explicit. The planner parent itself has >=99.99%
  child coverage in every case, so the fallback finding is directly measured even where whole-Core
  coverage is below the 90% fine-grained rule.
- Browser/client timing was unavailable. Runner n8n product wall includes the Docker-bridge n8n
  webhook and response parsing; it must not be called browser, Cloudflare, or pure n8n time.

## P1C recommendation (not implemented)

Select **one target: eliminate the recurring Luna structured-result envelope mismatch while
preserving the existing validator and Sol fallback**. This is evidence-backed because every Luna
provider response completed but failed the same bounded local validation code, forcing 7/7 Sol
fallbacks. The likely saving is the measured Sol fallback time and its $0.3289400 observed cost,
provided live semantic sentinels show Luna's corrected contract remains safe. Do not weaken
validation, remove fallback, change models, or optimize prompt size before that review.

The next candidates are (1) investigate fixed planner prompt/schema payload only after the
fallback issue is isolated, because input size is demonstrably large but not yet proven causal;
and (2) investigate index refresh on writes, where 4.651 s was measured across three writes.
