# ADR 0003: Phase 11B.1 OpenAI contextual-reasoner validation

- Status: Accepted — Sol selected as the Phase 11 contextual-resolution quality baseline
- Date: 2026-08-18

## Context

Phase 11A established that a strong contextual reasoner can decide among Phase 10 candidates, while
Odyssey Core must validate every result and fail closed. Phase 11B.1 needed to identify the cheapest
OpenAI API model that met a deliberately strict quality and safety bar without wiring contextual
resolution into entity creation or update.

Cost is a product constraint because later Odyssey stages will also require LLM calls. The benchmark
therefore tested models sequentially and stopped at the first sufficiently safe model rather than
benchmarking for global model strength:

```text
11B.1a zero-shot:    Luna --fails--> Terra --fails--> Sol --fails accuracy--> no passing model
11B.1b few-shot:     Luna --fails safety--> Terra --fails safety--> Sol --passes
                                                                         |
                                                                         +--> repeat passes
                                                                              (90/90 identical decisions)
```

## Decision boundary

The benchmark introduces only a small `ContextualReasoner` boundary, an OpenAI Responses API adapter,
and deterministic Core validation. It does not compose the reasoner with Phase 9 exact resolution,
Phase 10 retrieval, entity creation, entity update, or any production workflow. Phase 9 and Phase 10
behavior are unchanged.

Each request contained one synthetic reference, its context and canonical type, and only the Phase 10
Top-5 candidate IDs and textual evidence. Requests used `store: false`, medium reasoning, and strict
JSON-schema Structured Outputs. They never contained expected answers, case IDs, benchmark scoring
metadata, prior answers, or real vault content.

Core independently requires exactly `outcome` and `id`, one allowed outcome, a non-null supplied ID
for `RESOLVED`, and a null ID for either abstention. Invalid model output fails closed.

## Quality gate

A model provisionally passed only with zero clear false `RESOLVED`, zero invalid responses, at least
33/35 correct resolved cases, and at least 95% overall frozen-label accuracy. E13 remains frozen as
`AMBIGUOUS`, retains its `label_disputed` annotation, and is reported separately from clear false
resolutions.

## Phase 11B.1a: zero-shot evidence and escalation

| Model | Correct R / A / U | Clear false R | E13 disputed R | Overall | Invalid | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `gpt-5.6-luna` | 34 / 23 / 25 | 1 | 1 | 82/90 (91.11%) | 0 | Failed; escalate |
| `gpt-5.6-terra` | 35 / 22 / 25 | 2 | 1 | 82/90 (91.11%) | 0 | Failed; escalate |
| `gpt-5.6-sol` | 35 / 24 / 26 | **0** | 1 | 85/90 (94.44%) | 0 | Failed accuracy gate |

Luna was not repeated because its first run failed. Terra used the unchanged benchmark, prompt,
contract, reasoning effort, validation, and gate; it also failed and was not repeated. Before Sol,
measured Luna/Terra usage implied a $0.29–$0.33 run. The human explicitly approved that single run.
Sol was not repeated because it did not pass provisionally and the human required a report before any
additional paid run.

Sol was materially safer than Luna and Terra: it produced no clear false resolution and achieved the
best frozen-label accuracy. It nevertheless missed the 95% gate by one case. The five frozen-label
errors were four conservative `AMBIGUOUS`→`UNRESOLVED` distinctions plus disputed E13; there was no
clear unsafe link. The frozen gate is applied as approved rather than changed after observing results.

## Token usage and cost

| Model | Input | Cached input | Output | Reasoning | Calculated spend |
| --- | ---: | ---: | ---: | ---: | ---: |
| Luna | 34,977 | 0 | 5,145 | 2,918 | $0.013169 |
| Terra | 34,977 | 0 | 3,979 | 1,736 | $0.117702 |
| Sol | 34,977 | 0 | 3,810 | 1,613 | $0.289185 |
| **Total** | **104,931** | **0** | **12,934** | **6,267** | **$0.420056** |

Costs use actual API-reported tokens and the official standard list prices checked on the 2026-08-17
benchmark date: Luna $0.20/$0.02/$1.20, Terra $2.00/$0.20/$12.00, and Sol
$5.00/$0.50/$30.00 per million input/cached-input/output tokens. Current official model
documentation was rechecked on 2026-08-18 and lists the same
[Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) and
[Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra) prices; Sol remains
$5.00/$0.50/$30.00. Both price bases charge cache writes at 1.25x uncached input. These figures are
calculated estimates from the recorded counters, not an independent provider invoice. No call
reported cached input or cache writes. There were 270 evaluated requests, no retries, and no extra
smoke test.

Complete compact results are version controlled in
[`phase11b1_openai_results.md`](../../benchmarks/phase11b1_openai_results.md) and the three linked
per-case JSON artifacts. Raw Responses API documents and logs are not retained.

The original Phase 11B.1a conclusion remains: under the zero-shot prompt, no model passed every gate.
This evidence is preserved unchanged rather than reinterpreted after the later prompt-parity review.

## Phase 11B.1b: frozen few-shot prompt parity

Architecture review identified a material experimental mismatch: the successful manual Phase
11A.2/11A.3 configuration had used the ten labelled calibration examples already frozen in
`phase11a_contextual_resolution_cases.json`, while Phase 11B.1a had tested only abstract outcome
definitions. The mismatch was especially relevant because Sol's four clear zero-shot errors were
conservative `AMBIGUOUS`→`UNRESOLVED` distinctions.

Phase 11B.1b therefore added every and only those ten pre-existing examples. They predate the API
results and were not selected or changed in response to observed failures. Each example used the same
label-free request shape and Phase 10 Top-5 evidence as an evaluation case, followed by its frozen
decision as an assistant turn. Case IDs, split/category/language metadata, retrieval scores, and
plausible-ID scoring metadata were omitted. Evaluation truth remained outside the provider contract.

The system instructions, evaluation cases, model output contract, `store: false`, Structured Outputs,
medium reasoning, deterministic validation, gate, scoring, and sequential cost policy were otherwise
unchanged.

| Model | Correct R / A / U | Clear false R | E13 disputed R | Overall | Invalid | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `gpt-5.6-luna` | 34 / 26 / 26 | 1 | 1 | 86/90 (95.56%) | 0 | Failed safety; escalate |
| `gpt-5.6-terra` | 35 / 26 / 26 | 2 | 1 | 87/90 (96.67%) | 0 | Failed safety; escalate |
| `gpt-5.6-sol` run 1 | 35 / 28 / 26 | **0** | 1 | **89/90 (98.89%)** | 0 | **Passed** |
| `gpt-5.6-sol` repeat | 35 / 28 / 26 | **0** | 1 | **89/90 (98.89%)** | 0 | **Passed** |

Luna and Terra crossed the overall-accuracy threshold but retained clear false resolutions, so each
failed and triggered the next cost tier. Sol passed every gate. It changed four decisions relative to
its zero-shot run and corrected all four clear zero-shot errors; disputed E13 remained its only
frozen-label error. After human review, one Sol consistency repeat was authorized. It reproduced all
90 outcome/ID decisions exactly, again passed every gate, and incurred no invalid response or clear
false resolution. No other model or paid evaluation was run for consistency.

| Model | Zero-shot → few-shot | Same decisions | Few-shot input / cache write / output | Calculated 1b spend |
| --- | ---: | ---: | ---: | ---: |
| Luna | 82/90 → 86/90 | 84/90 | 248,727 / 248,457 / 4,848 | $0.067986 |
| Terra | 82/90 → 87/90 | 84/90 | 248,727 / 248,457 / 3,866 | $0.668075 |
| Sol | 85/90 → 89/90 | 86/90 | 248,727 / 248,457 / 2,564 | $1.631126 |
| Sol repeat | — | 90/90 versus Sol run 1 | 248,727 / 248,457 / 2,889 | $1.640876 |

Phase 11B.1b calculated spend was $4.008063; calculated spend across 11B.1a and 11B.1b was
$4.428119. These estimates use the unchanged benchmark-date price basis documented above and actual
API token counters, including the reported cache-write tokens at 1.25x input price. Recalculating from
the recorded counters with the current 2026-08-18 Luna and Terra prices produces the same figures.
They are not an independent provider invoice. No cached-input tokens or retries were reported.

### Follow-up: input-cost optimization

The selected baseline currently repeats a large static ten-example prefix. Later work may separately
evaluate explicit prompt caching, fewer or shorter examples, and lower reasoning effort. No
optimization is accepted until controlled evaluation proves that it matches the selected Sol
baseline's safety and quality.

## Decision and consequences

Phase 11B.1a selected no model under its zero-shot prompt. For Phase 11 contextual resolution, the
human selects GPT-5.6 Sol with medium reasoning and the frozen ten-example few-shot prompt as the
quality baseline. It achieved 35/35 correct `RESOLVED`, zero clear false `RESOLVED`, zero invalid
outputs, and 89/90 official frozen-label accuracy, with disputed E13 as its sole official error. An
independent repeat reproduced all 90 outcome/ID decisions exactly. Human selection is complete;
future cost optimizations must prove that they preserve this baseline's safety and quality before
replacing it. No further paid evaluation is authorized by this ADR.

Phase 11B production work remains open. Before real personal data is sent externally it must minimize
candidate evidence, investigate useful pseudonymization or anonymization, and explicitly review API
retention and project configuration. This benchmark does not implement those mechanisms, fallback
chains, human-in-the-loop behavior, multi-provider infrastructure, `upsert_entity`, or Phase 12.

## Limitations

- The evidence is synthetic and covers one frozen 90-case set.
- Luna and Terra have one run per prompt variant; Sol few-shot consistency has two runs on one frozen
  90-case set and does not establish broader repeatability.
- Frozen accuracy treats disputed E13 as wrong, as required.
- Token-based calculated cost may differ from the provider's final invoice.
- A benchmark result does not establish production privacy readiness or safe end-to-end entity writes.
