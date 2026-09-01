# Phase 17E retrieval reduction and answer-path evidence

Status: **evidence checkpoint complete; production Combined remains deferred**

## Objective

Close the remaining evidence gap between the adopted **Combined Top-500 candidate retrieval** and the
grounded relevant evidence that a higher layer may choose to provide to a strong model.

The adoption benchmark proved candidate recall, not safe semantic reduction. A relevant required fact can
occur as deep as Combined rank 412 in the frozen scale fixture. Therefore retrieval must not silently
turn the Top-500 candidate pool into an arbitrary fixed Top-N final context and thereby destroy the recall
that motivated Top-500.

This subphase must determine whether irrelevant candidates can be removed safely and economically before
production `ContextIndex` / `get_context` behavior changes. It does **not** own the caller's final context
budget. Any final context/token budget remains a higher-layer input or policy and must not be invented by
retrieval.

```text
query
  |
  v
Combined Top-500 candidates
  |
  +--> fused-rank-only baseline (diagnostic, not production policy)
  |
  `--> Luna high-recall relevance selector
            |
            +--> supplied relevant fact locators
            `--> explicit ESCALATE when unsafe to reduce
  |
  v
authoritative Markdown re-grounding
  |
  v
grounded relevant evidence
  |
  v
higher layer decides its context budget / use
  |
  v
focused Sol answer-path evidence
```

## Acceptance criteria

1. Reuse the frozen Phase 17E retrieval corpus and existing required-entity / required-fact oracles.
   Do not replace difficult cases merely to obtain cleaner results.
2. Recover or regenerate the **smallest required real MiniLM Combined evidence**. Prefer any preserved
   runtime ranking artifact if one exists. If regeneration is required, run Combined only where possible,
   persist the complete ranking output for reuse, and add progress visibility rather than repeatedly
   rerunning a silent full three-arm benchmark.
3. Establish a fused-rank-only **diagnostic baseline** showing how required-fact retention changes when a
   downstream consumer naively takes progressively smaller prefixes of the Top-500 ranking. These widths
   are benchmark observations only, not a production retrieval contract. The known rank-412 case must
   remain visible as a sentinel.
4. Benchmark `gpt-5.6-luna` as a **bounded high-recall relevance selector over supplied Combined fact
   candidates**. Luna may return only supplied fact locators or an explicit escalation outcome; it must
   not answer the user, summarize facts, invent knowledge, resolve write identity, mutate anything, or be
   forced to return a predetermined number of facts.
5. Start with the cheapest Luna reasoning configuration that is realistically supported by the existing
   provider boundary. Escalate the benchmark configuration only if the cheaper configuration fails the
   recall/safety gate; do not select a more expensive Luna configuration without evidence.
6. Measure selector safety primarily by **required-fact retention**. Dropping a required fact is the
   critical failure. Retaining extra distractors is acceptable; report how much evidence remains so cost
   can be evaluated without imposing an arbitrary selector width.
7. Include an explicit fail-safe path for selector uncertainty. Benchmark whether an `ESCALATE` outcome
   can preserve correctness by retaining the broader grounded candidate evidence for the higher/stronger
   path instead of guessing a narrow subset.
8. Run a focused live **retrieval -> grounded evidence -> `gpt-5.6-sol` answer** check on a compact set of
   representative and difficult cases, including multi-fact questions and the deep-rank sentinel. For
   this benchmark, the answer-path harness may apply an explicit experiment input/budget where needed,
   but that budget belongs to the harness/caller and must not become a retrieval-owned constant. This is
   benchmark evidence only; it does not add a production answer-generation service before Phase 18.
9. Compare at least:
   - required-fact retention after relevance reduction;
   - number and token size of evidence units retained by Luna without forcing a target width;
   - final answer correctness on the focused Sol set;
   - Luna input/output/reasoning tokens;
   - Sol input/output/reasoning tokens;
   - total estimated/real provider cost where usage data supports it;
   - latency;
   - selector escalation rate;
   - unsafe non-escalation / dropped-required-fact cases.
10. Preserve Markdown as source of truth and re-ground every selected locator against the current parsed,
    validated note before it can become answer context. Derived ranking or Luna output remains evidence
    only.
11. End with one explicit recommendation for the subsequent production implementation:
    - deterministic relevance reduction is sufficient;
    - Luna selector + strong-model/higher-layer fallback;
    - no semantic reducer is justified and the higher layer should consume the broader grounded evidence
      according to its own budget; or
    - defer Combined production adoption if no path preserves quality economically.
12. Update the Phase 17E adoption contract and Functional Roadmap if evidence changes the final-context
    policy adopted in PR #73. Preserve the ownership rule that retrieval returns grounded evidence while
    the caller/higher layer owns any final context budget.

## Architecture challenge

Result: **RECONSIDER**

Material concern:
The PR #73 adoption contract separates Top-500 candidate breadth from final context, but treating the
existing caller `context_limit` as a retrieval-owned truncation rule would discard required evidence that
the benchmark only recovers at deep ranks. Production implementation could therefore erase the very
recall advantage that justified Top-500.

Simpler alternative:
Do not invent a production context assembler, fixed final fact count, or retrieval-owned context budget.
First run one focused reduction benchmark using the existing Combined evidence boundary. Compare a naive
fused-rank prefix only as a diagnostic baseline against a bounded Luna relevance selector with explicit
escalation, then validate the resulting grounded evidence with a small Sol answer set. Let the higher
layer continue to own its own context budget.

Trade-offs:
This adds one evidence subphase and potentially one cheap model call to the eventual read path, but avoids
shipping a reducer known to be capable of dropping deep relevant facts. Luna must earn its extra cost and
latency with measured net savings and preserved recall; otherwise it is not adopted. Allowing the selector
to retain a variable number of relevant facts may yield larger payloads for genuinely broad questions,
which is appropriate; a higher layer can apply its own explicit budget when necessary.

Recommendation:
Run the focused relevance-reduction and answer-path evidence before production Combined implementation.
Keep the current whole-note production behavior unchanged until the reduction contract is closed. Do not
freeze a retrieval-owned final context size.

Human decision required: **NO**. The user has clarified that final context sizing belongs above retrieval,
and Odyssey's established evidence-before-model-change rule requires validating the relevance-reduction
boundary before production adoption.

## Out of scope

- production `ContextIndex` / `get_context` Combined implementation;
- defining a fixed production number of facts/notes that retrieval must return to the caller;
- changing the canonical schema, atomic-fact format, planner prompt, writer, or identity authority;
- Phase 18 / n8n integration;
- a new vector database, graph retrieval, learned reranker, or new service;
- replacing MiniLM;
- changing the production planner from Sol to Luna; the separate future Luna -> Sol planner-routing
  experiment remains deferred;
- general answer-generation architecture or a permanent answer-model contract before the first E2E.

## Open decisions

The benchmark must close these before implementation:

- whether a Luna selector is safe enough to remove irrelevant material from Top-500 while preserving
  required facts;
- the selected Luna reasoning configuration, if any;
- the observed evidence-size/token reduction and escalation behavior justified by evidence, without
  imposing a fixed selector output width;
- whether rare escalation may economically retain broader grounded evidence for the higher/stronger path;
- whether the resulting total cost/latency is better than the simplest direct alternative without losing
  answer quality.

The final caller context budget is **not** an open retrieval decision; it remains owned by the higher
layer/caller.

## Evidence checkpoint

The complete Combined ranking artifact was recovered from the frozen 1,000-entity corpus using the
existing MiniLM artifact and persisted outside the repository for reuse. The run took approximately
217 seconds to load the model, 201 seconds to build Combined vectors, and 8.7 seconds to query the
22-case suite. The `scale-100` required fact remains at fused rank 412.

The diagnostic fused-prefix baseline retained all required facts for 63.2% of cases at Top-5, Top-10,
and Top-20; 94.7% at Top-200, Top-300, and Top-400; and 100% only at Top-500. These are observations,
not production limits.

The benchmark-only selector implementation is in `benchmarks/phase17e_retrieval/reduction.py`. Its
closed output is `SELECT` with supplied locators or `ESCALATE` with no locators. It rejects unknown
and duplicate locators, re-grounds selected facts from validated current benchmark notes, and never
owns a context budget or answer authority.

The initial in-sandbox smoke test failed with `APIConnectionError` and was correctly recorded as
`PROVIDER_ERROR` / `NO_EVIDENCE`. A subsequent manual Raspberry-shell run produced valid evidence for
all 22 cases using `gpt-5.6-luna` with reasoning `none`: 21 `SELECT`, one semantic `ESCALATE` (`q2`),
and no provider errors. `SELECT` retained all required facts for 19/21 valid selections, but dropped
required facts without escalation in two cases: `scale-100` and `scale-700`. This is a safety-gate
failure, despite strong natural compression: selected facts averaged/median 3.6/2 (min 1, max 27),
with average retained evidence of 1.8%. Luna usage was 400,560 input tokens, 1,065 output tokens,
and zero reasoning tokens. The 400,560-token Luna input is an important cost signal for the later
comparison and is not itself evidence of savings.

The harness now supports `--reasoning none|low|medium|high` and repeated `--case ID` filters, while
retaining the full-suite default. The reasoning choices are benchmark-only and do not change production
configuration. Because `none` failed the safety gate, the revised selector prompt is being tested from
the cheapest effort upward on only `scale-100`, `scale-700`, and `q2`. If a targeted run is safe
(`SELECT` with all required facts or semantic `ESCALATE`), the next broader run is permitted; any unsafe
non-escalated drop stops that effort's experiment. The focused Sol answer-path suite remains unrun until
the revised selector clears its staged safety gate.

The prior original-prompt runs remain historical evidence, not validation of the revised prompt. The
two unsafe `none` cases expose an ambiguity between retaining enough evidence to identify an answer
entity and retaining evidence supporting every material query constraint. The revised instruction now
requires evidence for every condition in conjunctive queries and escalation when that cannot be done
confidently. Codex cannot access the provider; live runs are performed manually from the Raspberry shell.

## Decision

**D. Production Combined should remain deferred.** Luna/none has valid provider evidence but fails the
safety gate through two unsafe non-escalated required-fact drops. Luna/low is justified and remains a
staged experiment, not yet a production decision. Until that experiment and the compact Sol suite are
complete, the caller/higher layer continues to own any final context budget and production retrieval
remains unchanged.
