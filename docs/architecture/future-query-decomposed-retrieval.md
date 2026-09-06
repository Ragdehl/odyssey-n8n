# Future Retrieval Refinements

Status: **deferred until realistic Odyssey Online usage exposes concrete retrieval misses or candidate-cost pressure**.

Production retrieval remains the existing whole-note path. Phase 17E synthetic evidence showed that an experimental Combined strategy could still miss required target-entity facts even at large Top-K, so it was not adopted. This document preserves the next experiments without making them prerequisites for the MVP.

## Experiment order

Do not start with another model ladder or infrastructure layer. Test the smallest explanation for the observed failures first.

### 1. Query-decomposed multi-fact retrieval

Conjunctive requests may contain several distinct clues that one whole-query embedding does not represent well. Test decomposing the request into meaningful retrieval elements and aggregating fact evidence by canonical entity.

```text
user request
    |
    v
meaningful elements E1 / E2 / E3
    |          |          |
    v          v          v
local fact retrieval per element
    |          |          |
    +-----+----+----------+
          |
          v
aggregate by canonical entity
          |
          +--> reward coverage of distinct elements
          +--> retain element -> fact -> entity provenance
          `--> do not count duplicate evidence as new coverage
```

Example:

```text
"¿Quién trabaja en Thales, estudió en Toulouse y disfruta escalando?"

Marta covers E1 + E2 + E3
Distractor strongly covers only E1
```

A future benchmark should decide how elements are produced, how semantic strength and coverage combine, how optional/contradictory clauses are represented, and whether this improves real recall/cost/latency. Start with the smallest scoring rule that rewards **distinct element coverage** before testing learned rerankers, graph retrieval, another embedding model, or new infrastructure.

### 2. High-recall candidate reduction if candidate volume becomes costly

Earlier large-vault stress evidence showed a recall-first asymmetry: local MiniLM kept the expected contextual entity much more reliably at broad Top-K than at aggressive Top-K. If real candidate volume makes strong-model context expensive, benchmark an inexpensive **selector**, not an identity authority:

```text
broad local candidates
       |
       v
bounded inexpensive selector (for example Luna if still justified)
       |
       +--> retain ~20 / ~10 candidates
       `--> dropping the correct candidate = critical failure
       |
       v
strong contextual resolver when identity reasoning is required
```

Measure Recall@20/10/5, exact dropped IDs, Spanish/French/contextual cases, source-note length, latency, tokens, and real cost. A nicer ranking is insufficient if correct candidates disappear.

Only after high-recall selection is proven should Odyssey test whether the cheaper model can itself resolve some identities with fail-closed escalation.

### 3. Compact revision-bound retrieval evidence if full bodies are wasteful

A future derived index may expose compact identity/retrieval evidence such as:

```text
stable id | canonical name | type | aliases | compact identity-bearing facts
```

This can reduce provider input, but stale identity summaries are dangerous. Prefer revision-bound rebuildable derived evidence before adding another canonical Markdown property. Rebuilding the index must not unexpectedly require cloud LLM calls unless that cost/contract is explicitly accepted.

Atomic-fact retrieval is another rebuildable projection hypothesis; success would change retrieval evidence selection, never write authority.

## Benchmark guardrails

- Keep canonical entity identity attached to every fact/evidence item.
- Re-ground selected evidence against current authoritative Markdown before model use when required by the active contract.
- Preserve difficult historical synthetic cases, but add failures observed through real Odyssey Online use rather than optimizing only the old corpus.
- If the historical large-vault fixture is extended for selector/fact tests, include short (~1–5 factual units), medium (~10–20), long (~40–60), and very long (~1,500–3,000 words) heterogeneous notes; place identity-bearing evidence deliberately at the beginning/middle/end of different notes, include distractors sharing names/organizations/places/vocabulary, and report recall by length bucket.
- Measure whole-note/fact/query-element behavior separately enough to identify where recall is lost.
- Do not revive an entity-agnostic / “without entity” variant unless real evidence shows that canonical entity grouping itself is causing the miss.
- Do not add a vector database, graph database, local LLM service, or new long-lived component merely to run the experiment.
- Retrieval relevance never authorizes mutation.

## Adoption rule

Change production retrieval only after a frozen comparison demonstrates a material improvement on the actual failure mode without unacceptable recall, latency, resource, token, or cost regression. If real usage does not expose a problem, leave production retrieval alone.
