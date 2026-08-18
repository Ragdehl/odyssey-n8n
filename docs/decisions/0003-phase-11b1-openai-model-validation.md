# ADR 0003: Phase 11B.1 OpenAI contextual-reasoner validation

- Status: Accepted — Sol selected as the Phase 11 contextual-resolution quality baseline; Phase 11B.1c complete
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

Benchmark cost estimates use the
[OpenAI API prices announced effective 2026-07-30](https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/):
Luna $0.20/$0.02/$1.20, Terra $2.00/$0.20/$12.00, and Sol $5.00/$0.50/$30.00 per
million input/cached-input/output tokens, with cache writes at 1.25x uncached input. Individual
model-detail pages displayed inconsistent earlier Luna and Terra prices at final review time, so they
are not the pricing source for these estimates. The figures use actual API-reported token counters
and are calculated estimates, not an independent provider invoice. No call reported cached input or
cache writes. There were 270 evaluated requests, no retries, and no extra smoke test.

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
$4.428119. These estimates use the 2026-07-30 price basis documented above and actual API token
counters, including the reported cache-write tokens at 1.25x input price. They are not an independent
provider invoice. No cached-input tokens or retries were reported.

### Follow-up: input-cost optimization

Phase 11B.1c investigated only three bounded opportunities against the selected baseline.

- Exact identity matching now uses NFC Unicode normalization and repeated-whitespace collapse in
  addition to its existing trimming and case folding. It deliberately preserves accents, articles,
  prepositions, punctuation, hyphens, apostrophes, and stopwords. Known primary names and aliases
  should eventually be detectable locally inside an incoming message through a derived lookup/index;
  that message interpreter remains future work.
- A single policy selected from the ten existing calibration rows (`top_score >= 0.3895420472` and
  `top_score - second_score >= 0.1163190872`) was evaluated once against the existing 90 blocking
  cases. It auto-resolved 34/90 cases, including only 21 correct resolutions and 13 clear false
  `RESOLVED` decisions; disputed E13 was not auto-resolved. Because safety requires zero clear false
  resolutions, the semantic fast path is rejected/deferred. The resolver remains exact → Phase 10
  Top-N → Sol → deterministic Core validation.
- The frozen Sol few-shot prefix is now structured for GPT-5.6 explicit-only Responses API caching:
  the final calibration user turn carries the supported `input_text` breakpoint, followed by
  assistant example 10 and the changing evaluation request, with a stable `prompt_cache_key` and
  `store: false`. The two-request synthetic smoke used existing cases `en-xavi-partner` and `A01`.
  Request 1 reported 2,777 input / 2,518 cache-write / 0 cached / 25 output tokens; request 2
  reported 2,782 input / 0 cache-write / 2,518 cached / 26 output tokens. The combined estimated
  spend was $0.021142. Cache reuse therefore succeeded. This was transport validation only, not a
  quality benchmark, and the baseline prompt and contract remain unchanged.

The provider's explicit GPT-5.6 cache TTL is approximately 30 minutes and refreshes when the cached
prefix is reused. Caching is therefore useful mainly for bursts or sessions containing several
requests. For isolated Odyssey captures separated by hours, the entry may expire before reuse and
cache writing can cost more than uncached input. Prompt caching is an opportunistic optimization,
not the foundation of Odyssey's cost model. Final production activation policy remains deferred to
Phase 11B.2 or later integration; no scheduler or session manager is introduced here.

### Phase 11B.1c closure evidence

The bounded retrieval follow-up is complete. Safer exact matching is accepted: NFC normalization,
case folding, repeated-whitespace collapse, and preservation of identity-bearing lexical differences.
The strong contextual-reasoner boundary and the Sol few-shot baseline remain accepted. Explicit Sol
prompt caching is technically validated and is retained as an opportunistic optimization for bursts,
with an approximately 30-minute reuse window; it is not a foundation for the cost model.

The frozen 1,000-note, 40-query adversarial fixture produced the following contextual-only MiniLM
recall: 72% at Top-5, 80% at Top-20, 88% at Top-50, and 100% at Top-100. This is evidence that the
current fixture's main risk is candidate reduction/ranking rather than total broad discovery failure,
not proof of arbitrary future real-vault recall. The tested cosine identity fast path remains
rejected after 13 clear false `RESOLVED` decisions. The WordNet/OMW hybrid and tested mMARCO
Cross-Encoder reranker are rejected/deferred: the latter did not improve contextual Top-5 beyond
72% and added substantial ARM64 resource cost.

The resulting boundary remains:

```text
exact unique
    -> resolved locally
otherwise:
broad local candidate retrieval
    -> future safe candidate reduction, if needed
    -> strong contextual reasoner
    -> deterministic Core validation
```

No production retrieval dependency or pipeline change was adopted. Future candidate reduction and
compact per-note retrieval summaries are tracked in GitHub issue #20; they are not Phase 11B.1c
implementation.

Future resolver-cost architecture remains deliberately deferred to later phases. The eventual
`interpret_request` + entity-reference extraction + `decompose_knowledge` flow should be one
intelligent model operation, benchmarked cheapest-first independently of Sol. Known names and
aliases should be detected locally; multiple unresolved references from one message should be
considered for one contextual request; evidence minimization must wait for Phase 11B.2 privacy
validation. Sophisticated fuzzy/near-exact matching, stopword or preposition removal, fewer
calibration examples, Top-5 → Top-3, medium → low reasoning, compressed identity evidence,
broader batching, provider/model experiments, distillation, and asynchronous Batch API processing
are all deferred until Odyssey is materially usable.

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
