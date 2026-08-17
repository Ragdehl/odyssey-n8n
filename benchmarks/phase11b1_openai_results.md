# Phase 11B.1 OpenAI contextual-reasoner results

Three models were tested sequentially, cheapest first, against the same 90 unique frozen synthetic
Phase 11A blocking cases. Each request resolved one reference, used the Phase 10 Top-5 candidate
evidence, set `store: false`, requested medium reasoning and strict Structured Outputs, and excluded
case identity, expected labels, scoring metadata, and previous answers.

| Model / run | Correct R / A / U | Clear false R | Disputed E13 R | Overall | Accuracy when resolved | Coverage | Invalid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` / 1 | 34 / 23 / 25 | 1 | 1 | 82/90 (91.11%) | 34/36 (94.44%) | 36/90 (40.00%) | 0 |
| `gpt-5.6-terra` / 1 | 35 / 22 / 25 | 2 | 1 | 82/90 (91.11%) | 35/38 (92.11%) | 38/90 (42.22%) | 0 |
| `gpt-5.6-sol` / 1 | 35 / 24 / 26 | **0** | 1 | 85/90 (94.44%) | 35/36 (97.22%) | 36/90 (40.00%) | 0 |

E13 (`en-toulouse-supermarket`) remains frozen as `AMBIGUOUS` and retains its existing
`label_disputed` annotation. All three models selected `carrefour-market-capitole`; it is reported
separately and still counts as wrong in frozen-label accuracy.

| Model / run | Mean / median / p95 latency | Input | Cached input | Output | Reasoning | Calculated spend |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` / 1 | 1.352 / 1.201 / 2.992 s | 34,977 | 0 | 5,145 | 2,918 | $0.013169 |
| `gpt-5.6-terra` / 1 | 1.491 / 1.246 / 3.437 s | 34,977 | 0 | 3,979 | 1,736 | $0.117702 |
| `gpt-5.6-sol` / 1 | 2.057 / 1.556 / 3.183 s | 34,977 | 0 | 3,810 | 1,613 | $0.289185 |
| **Total** | — | **104,931** | **0** | **12,934** | **6,267** | **$0.420056** |

Spend is calculated from actual API-reported token usage and official standard prices checked on
2026-08-17: Luna $0.20/$0.02/$1.20, Terra $2.00/$0.20/$12.00, and Sol
$5.00/$0.50/$30.00 per million input/cached-input/output tokens. It is not an independent billing
invoice. No request reported cached input or cache-write tokens, and no transient retry occurred.

Luna failed and was not repeated. Terra was therefore tested, failed, and was not repeated. Sol was
tested once after explicit approval of the estimated spend. Sol eliminated clear false resolutions
and was best on every quality measure, but 85/90 is 94.44%, below the required 95% frozen-label gate.
No model passed, so Phase 11B.1 makes no provisional production-model recommendation. Per the approved
scope and cost control, no prompt tuning or additional paid repeat was performed.

The compact per-case records, including decisions, schema validity, correctness, false-resolution
status, latency, and token counters, are preserved in:

- [`phase11b1_luna_run1.json`](phase11b1_luna_run1.json)
- [`phase11b1_terra_run1.json`](phase11b1_terra_run1.json)
- [`phase11b1_sol_run1.json`](phase11b1_sol_run1.json)
