# Future query-decomposed multi-fact retrieval

Status: **deferred near-term retrieval refinement; does not block Phase 18**

## Why this is preserved

Phase 17E corrected the retrieval benchmark to keep canonical entity identity attached to required facts.
That audit exposed a concrete weakness in the current experimental Combined score: each fact receives its
own entity + fact reciprocal-rank score, but the ranking does not explicitly reward one entity for jointly
covering several distinct parts of a conjunctive request.

The `scale-100` and `scale-700` cases are useful sentinels for that limitation. They do not justify more
pre-E2E retrieval experimentation by themselves. Odyssey should first move into the real n8n/E2E path and
return to this question with actual usage evidence.

## Preserved hypothesis

A later retrieval experiment should test whether a search request can be decomposed into several
meaningful retrieval elements and whether fact evidence can then be aggregated by canonical entity.
Conceptually:

```text
user search request
        |
        v
meaningful retrieval elements
   E1      E2      E3
    |       |       |
    v       v       v
 MiniLM fact retrieval per element
    |       |       |
    `---+---+---+---'
        |
        v
aggregate evidence by canonical entity
        |
        +--> reward coverage of more distinct request elements
        +--> keep element -> fact -> entity provenance visible
        `--> avoid rewarding duplicate matches for the same element as if they were new coverage
        |
        v
high-recall entity/fact candidates
        |
        +--> optional Luna reduction / escalation if later evidence justifies it
        `--> Sol or the higher-level answer/resolution path receives grounded evidence
```

The motivating intuition is simple: if a request contains several independent clues, the entity whose
facts satisfy the largest number of those clues is often a stronger candidate than an entity that scores
very highly against only one clue. This may be easier for the existing local MiniLM stage to surface than
asking one embedding/ranking score to represent the entire conjunctive request at once.

Example:

```text
request: "¿Quién trabaja en Thales, estudió en Toulouse y disfruta escalando?"

E1 = trabaja en Thales
E2 = estudió en Toulouse
E3 = disfruta escalando

Marta:
  E1 -> matching fact
  E2 -> matching fact
  E3 -> matching fact
  coverage = 3/3

Other note:
  E1 -> very strong matching fact
  E2 -> no evidence
  E3 -> no evidence
  coverage = 1/3

Hypothesis: Marta should rise because one canonical entity jointly covers more of the request.
```

## What is deliberately undecided

This document does not choose a production algorithm. A future benchmark must determine:

- how the request is decomposed and whether the existing planner can provide the elements safely;
- whether MiniLM runs one search per element or an equivalent batched operation;
- how coverage and semantic/rank strength are combined without overfitting to the synthetic fixture;
- how contradictory or optional request elements are represented;
- how many candidates move to Luna/Sol and whether Luna still provides a useful reduction step;
- whether this actually improves real recall, latency, token use, and answer quality after the first E2E.

Prefer the smallest scoring rule that rewards **distinct element coverage** before testing learned
rerankers, graph retrieval, another embedding model, or new infrastructure.

## Guardrails

- Canonical entity identity stays attached to every fact; repeated fact text from another entity never
  satisfies the target entity's evidence.
- Retrieval remains evidence-only and never becomes autonomous write authority.
- Selected facts must still be re-grounded against authoritative current Markdown before model use.
- Do not add a vector database, graph database, local LLM, or new service merely for this experiment.
- Preserve difficult frozen cases, including `scale-100` and `scale-700`, but add real E2E-derived cases
  when available rather than optimizing only for the synthetic corpus.
- Do not spend more pre-E2E benchmark effort on an entity-agnostic / "without entity" variant. The current
  product model is entity-note based, and the next useful experiment is the explicit multi-element,
  entity-coverage hypothesis above. Revisit entity-agnostic retrieval only if later real evidence shows
  that canonical entity grouping itself is causing a concrete failure.

## Placement

This is intentionally **not far-future work**, but it is also not a prerequisite for the first E2E.
Revisit it after Phase 18 has produced a real retrieval/answer path, preferably as an early
Phase 19 evidence-driven refinement before broader retrieval optimization.

Until then, current production whole-note retrieval remains unchanged. The corrected Phase 17E evidence
should be treated as a reason to avoid prematurely implementing the previously assumed Combined Top-500
strategy, not as a reason to delay Phase 18 with more synthetic retrieval combinations.
