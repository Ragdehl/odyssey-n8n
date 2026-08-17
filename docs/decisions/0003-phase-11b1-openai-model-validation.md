# ADR 0003: Phase 11B.1 OpenAI contextual-reasoner validation

- Status: Benchmark complete; no model selected; human decision required
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
Luna --fails--> Terra --fails--> Sol --fails accuracy gate--> human decision
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

## Evidence and escalation

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

Costs use actual API-reported tokens and official standard list prices checked on 2026-08-17. They
are calculated spend, not an independent provider invoice. No call reported cached input or cache
writes. There were 270 evaluated requests, no retries, and no extra smoke test.

Complete compact results are version controlled in
[`phase11b1_openai_results.md`](../../benchmarks/phase11b1_openai_results.md) and the three linked
per-case JSON artifacts. Raw Responses API documents and logs are not retained.

## Decision and consequences

No tested model meets every approved Phase 11B.1 gate, so no provisional production model is selected.
Sol is the strongest and only tested model with zero clear false resolutions, but adopting it, revising
the accuracy gate, changing the prompt, changing reasoning effort, or funding another run is a human
decision. No further paid evaluation is authorized by this ADR.

Phase 11B production work remains open. Before real personal data is sent externally it must minimize
candidate evidence, investigate useful pseudonymization or anonymization, and explicitly review API
retention and project configuration. This benchmark does not implement those mechanisms, fallback
chains, human-in-the-loop behavior, multi-provider infrastructure, `upsert_entity`, or Phase 12.

## Limitations

- The evidence is synthetic and covers one frozen 90-case set.
- Each model has one run only because none provisionally passed; consistency is therefore unmeasured.
- Frozen accuracy treats disputed E13 as wrong, as required.
- Token-based calculated cost may differ from the provider's final invoice.
- A benchmark result does not establish production privacy readiness or safe end-to-end entity writes.
