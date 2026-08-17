# Phase 11A strong-reasoner results

The complete synthetic cases, frozen labels, normalized decisions, and Phase 11A.3 raw response are in
[`phase11a_strong_reasoner_cases.json`](phase11a_strong_reasoner_cases.json). Phase 11A.2 reuses the 20
notes and 10 calibration examples in
[`phase11a_contextual_resolution_cases.json`](phase11a_contextual_resolution_cases.json).

## Phase 11A.2

Two independent temporary ChatGPT conversations evaluated the same 48 blocking cases. Their decisions
were identical for all 48 cases.

| Metric | Frozen-label result |
| --- | ---: |
| Correct `RESOLVED` | 21/21 |
| Correct `AMBIGUOUS` | 14/15 |
| Correct `UNRESOLVED` | 12/12 |
| False `RESOLVED` | 1/48 |
| Overall | 47/48 |
| Accuracy when resolved | 21/22 (95.5%) |

E13 (`en-toulouse-supermarket`) remains frozen as expected `AMBIGUOUS` and is marked
`label_disputed`. Both runs returned `RESOLVED:carrefour-market-capitole`, the only supplied note
explicitly described as being in Toulouse. The official score is not changed retrospectively.

## Phase 11A.3

The prompt, decision contract, and calibration examples were frozen before the 42 fresh adversarial
cases were evaluated.

| Metric | Result |
| --- | ---: |
| Correct `RESOLVED` | 14/14 |
| Correct `AMBIGUOUS` | 14/14 |
| Correct `UNRESOLVED` | 14/14 |
| False `RESOLVED` | 0/42 |
| Semantic accuracy | 42/42 (100%) |
| Accuracy when resolved | 14/14 (100%) |
| Output-schema compliance | **FAILED** |

The response contained exactly 42 objects in A01→A42 order and every semantic decision was correct,
but every object omitted the requested `case_id`. The JSON artifact preserves the raw response and a
positional normalization. Semantic accuracy does not imply output-contract compliance.

## Combined frozen-label interpretation

| Metric | Result across 90 unique blocking cases |
| --- | ---: |
| Correct `RESOLVED` | 35/35 |
| Correct `AMBIGUOUS` | 28/29 |
| Correct `UNRESOLVED` | 26/26 |
| False `RESOLVED` | 1/90 |
| Official overall score | 89/90 |

The only false `RESOLVED` is disputed E13. These manual experiments demonstrate feasibility for a
sufficiently capable contextual reasoner under the tested contract. They do not establish that every
strong LLM or any specific API model is production-safe.
