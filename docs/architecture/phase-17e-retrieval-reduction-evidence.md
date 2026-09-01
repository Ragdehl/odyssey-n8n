# Phase 17E retrieval reduction and answer-path evidence

Status: **proposed focused subphase before production Combined implementation**

## Objective

Close the remaining evidence gap between the adopted **Combined Top-500 candidate retrieval** and the
small grounded context that a strong model should actually receive.

The adoption benchmark proved candidate recall, not safe final reduction. A relevant required fact can
occur as deep as Combined rank 412 in the frozen scale fixture. Therefore simply truncating the fused
ranking to the ordinary caller context limit can destroy the recall that motivated Top-500.

This subphase must determine the smallest reliable and economically useful reduction path before
production `ContextIndex` / `get_context` behavior changes.

```text
query
  |
  v
Combined Top-500 candidates
  |
  +--> deterministic truncation baseline
  |
  `--> Luna high-recall fact selector
            |
            +--> bounded selected fact locators
            `--> explicit ESCALATE when unsafe to reduce
  |
  v
authoritative Markdown re-grounding
  |
  v
focused Sol answer-path evidence
```

## Acceptance criteria

1. Reuse the frozen Phase 17E retrieval corpus and existing required-entity / required-fact oracles.
   Do not replace difficult cases merely to obtain cleaner results.
2. Recover or regenerate the **smallest required real MiniLM Combined evidence**. Prefer any preserved
   runtime ranking artifact if it exists. If regeneration is required, run Combined only where possible,
   persist the complete ranking output for reuse, and add progress visibility rather than repeatedly
   rerunning a silent full three-arm benchmark.
3. Establish deterministic truncation baselines for practical final evidence widths (at least the
   currently relevant small limits) and report required-fact retention separately from candidate recall.
   The known rank-412 case must remain visible as a sentinel.
4. Benchmark `gpt-5.6-luna` as a **bounded high-recall selector over supplied Combined fact candidates**.
   Luna may return only supplied fact locators or an explicit escalation outcome; it must not answer the
   user, summarize facts, invent knowledge, resolve write identity, or mutate anything.
5. Start with the cheapest Luna reasoning configuration that is realistically supported by the existing
   provider boundary. Escalate the benchmark configuration only if the cheaper configuration fails the
   recall/safety gate; do not select a more expensive Luna configuration without evidence.
6. Measure selector safety primarily by **required-fact retention**. Dropping a required fact is the
   critical failure. Retaining extra distractors is acceptable and should be traded against cost later.
7. Include an explicit fail-safe path for selector uncertainty. Benchmark whether an `ESCALATE` outcome
   can preserve correctness by sending the broader grounded candidate evidence to the strong-model path
   instead of guessing a narrow subset.
8. Run a focused live **retrieval -> grounded evidence -> `gpt-5.6-sol` answer** check on a compact set of
   representative and difficult cases, including multi-fact questions and the deep-rank sentinel. This
   is benchmark evidence only; it does not add a production answer-generation service before Phase 18.
9. Compare at least:
   - required-fact retention after reduction;
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
    - deterministic reduction only;
    - Luna selector + strong-model fallback;
    - broader direct strong-model context because reduction is not safe enough yet; or
    - defer Combined production adoption if no bounded path preserves quality economically.
12. Update the Phase 17E adoption contract and Functional Roadmap if evidence changes the final-context
    policy adopted in PR #73.

## Architecture challenge

Result: **RECONSIDER**

Material concern:
The PR #73 adoption contract separates Top-500 candidate breadth from final context, but its simple
fused-rank truncation can discard required evidence that the benchmark only recovers at deep ranks. With
ordinary small caller limits, production implementation could therefore erase the very recall advantage
that justified Top-500.

Simpler alternative:
Do not invent a production context assembler or implement an unvalidated truncation policy. First run one
focused reduction benchmark using the existing Combined evidence boundary. Compare deterministic
truncation against a bounded Luna locator selector with explicit escalation, then validate only the chosen
compact evidence path with a small Sol answer set.

Trade-offs:
This adds one evidence subphase and potentially one cheap model call to the eventual read path, but avoids
shipping a reducer known to be capable of dropping deep relevant facts. Luna must earn its extra cost and
latency with measured net savings and preserved recall; otherwise it is not adopted.

Recommendation:
Run the focused reduction and answer-path evidence before production Combined implementation. Keep the
current whole-note production behavior unchanged until the reduction contract is closed.

Human decision required: **NO**. The user has already requested the Luna cost-reduction experiment, and
Odyssey's established evidence-before-model-change rule requires validating the reduction boundary before
production adoption.

## Out of scope

- production `ContextIndex` / `get_context` Combined implementation;
- changing the canonical schema, atomic-fact format, planner prompt, writer, or identity authority;
- Phase 18 / n8n integration;
- a new vector database, graph retrieval, learned reranker, or new service;
- replacing MiniLM;
- changing the production planner from Sol to Luna; the separate future Luna -> Sol planner-routing
  experiment remains deferred;
- general answer-generation architecture or a permanent answer-model contract before the first E2E.

## Open decisions

The benchmark must close these before implementation:

- whether a Luna selector is safe enough to reduce Top-500 while preserving required facts;
- the selected Luna reasoning configuration, if any;
- the maximum compact selected-evidence width and escalation behavior justified by evidence;
- whether rare escalation may economically send broader grounded evidence to Sol;
- whether the resulting total cost/latency is better than the simplest direct alternative without losing
  answer quality.
