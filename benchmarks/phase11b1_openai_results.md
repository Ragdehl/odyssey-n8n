# Phase 11B.1 OpenAI contextual-reasoner results

## Phase 11B.1a: zero-shot baseline

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

## Phase 11B.1b: frozen few-shot prompt parity

Architecture review found that Phase 11B.1a had omitted the ten pre-existing labelled calibration
examples used by the successful manual Phase 11A.2/11A.3 experiments. Phase 11B.1b added every and
only those frozen examples, in their original order, as compact user/assistant turns. Example inputs
used their Phase 10 Top-5 evidence; example outputs contained the frozen outcome and ID. No example
contained its case ID, split, category, language, score, or plausible-ID scoring metadata. The final
evaluation turn remained blind, and all other request and scoring controls were unchanged.

| Model / run | Correct R / A / U | Clear false R | Disputed E13 R | Overall | Accuracy when resolved | Coverage | Invalid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` / 1b | 34 / 26 / 26 | 1 | 1 | 86/90 (95.56%) | 34/36 (94.44%) | 36/90 (40.00%) | 0 |
| `gpt-5.6-terra` / 1b | 35 / 26 / 26 | 2 | 1 | 87/90 (96.67%) | 35/38 (92.11%) | 38/90 (42.22%) | 0 |
| `gpt-5.6-sol` / 1b | 35 / 28 / 26 | **0** | 1 | **89/90 (98.89%)** | 35/36 (97.22%) | 36/90 (40.00%) | 0 |
| `gpt-5.6-sol` / 1b repeat | 35 / 28 / 26 | **0** | 1 | **89/90 (98.89%)** | 35/36 (97.22%) | 36/90 (40.00%) | 0 |

| Model | Zero-shot → few-shot overall | Decision consistency | Clear false R | Gate |
| --- | ---: | ---: | ---: | --- |
| Luna | 82/90 → 86/90 | 84/90 | 1 → 1 | Failed safety |
| Terra | 82/90 → 87/90 | 84/90 | 2 → 2 | Failed safety |
| Sol | 85/90 → 89/90 | 86/90 | 0 → 0 | **Passed** |

Few-shot calibration materially improved the distinction between `AMBIGUOUS` and `UNRESOLVED` for
all three models. It did not remove the clear false resolutions from Luna or Terra. Sol corrected all
four of its clear zero-shot errors; disputed E13 remained its only frozen-label error.

| Model / run | Mean / median / p95 latency | Input | Cache write | Cached input | Output | Reasoning | Calculated spend |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna` / 1b | 1.425 / 1.252 / 2.317 s | 248,727 | 248,457 | 0 | 4,848 | 2,568 | $0.067986 |
| `gpt-5.6-terra` / 1b | 1.307 / 1.189 / 2.147 s | 248,727 | 248,457 | 0 | 3,866 | 1,615 | $0.668075 |
| `gpt-5.6-sol` / 1b | 1.797 / 1.683 / 2.760 s | 248,727 | 248,457 | 0 | 2,564 | 385 | $1.631126 |
| `gpt-5.6-sol` / 1b repeat | 1.938 / 1.770 / 3.078 s | 248,727 | 248,457 | 0 | 2,889 | 698 | $1.640876 |
| **1b total** | — | **994,908** | **993,828** | **0** | **14,167** | **5,266** | **$4.008063** |

All few-shot runs reported cache-write tokens but no cached-input tokens. The calculated spend
uses the same dated standard prices as Phase 11B.1a, including OpenAI's 1.25x input rate for cache
writes. Across both API phases the calculated total is $4.428119. There were no retries.

Sol is the provisional cheapest passing prompt-parity candidate because both cheaper models failed
the unchanged safety gate. Its one authorized consistency repeat reproduced all 90 outcome/ID
decisions exactly (90/90, 100% decision consistency), including zero clear false resolutions and
disputed E13 as the sole frozen-label error. No further paid evaluation was performed.

The separate compact Phase 11B.1b per-case records are:

- [`phase11b1b_luna_run1.json`](phase11b1b_luna_run1.json)
- [`phase11b1b_terra_run1.json`](phase11b1b_terra_run1.json)
- [`phase11b1b_sol_run1.json`](phase11b1b_sol_run1.json)
- [`phase11b1b_sol_run2.json`](phase11b1b_sol_run2.json)
