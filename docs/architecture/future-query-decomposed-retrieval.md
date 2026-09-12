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

### Generic cross-note reasoning and matching

A request may need to combine several independent evidence sets rather than identify one entity from several clues. Treat that as a natural extension of generic Odyssey retrieval + grounded synthesis, not as a reason to create a bespoke application for every relationship pattern.

Representative examples:

- `¿Qué cosas podría hacer Xavi, mi amigo el electricista manitas?` — combine Xavi's profile/skills with relevant candidate knowledge (tasks are only one possible candidate set).
- `¿Qué regalo le podría gustar a Alice?` — combine a person's interests/preferences with products, ideas, or past purchases.
- `¿Qué recetas puedo hacer con lo que suelo comprar y lo que ya tengo?` — combine recipe knowledge with product/purchase/pantry-like evidence.
- `¿Qué opciones de vacaciones encajan con lo que nos gusta y con los niños?` — combine people/preferences/past-trip evidence with candidate destinations or plans.
- `¿Qué herramientas o materiales que ya tengo podrían servirme para arreglar esto?` — combine a problem/project with tool/material/product knowledge.
- `¿Qué personas que conozco podrían ayudarme con este tema?` — combine a topic/problem with people, roles, skills, and relationship knowledge.
- `¿Qué notas parecen relacionadas o contradictorias aunque nunca las haya enlazado?` — compare evidence across notes while keeping inference distinct from canonical facts.

Preferred generic shape:

```text
natural-language request
        |
        v
planner identifies independent evidence needs
        |
        +--> RetrieveAction / evidence set A
        +--> RetrieveAction / evidence set B
        `--> optionally more bounded sets
                    |
                    v
          grounded cross-set synthesis
                    |
                    v
     answer / comparison / recommendation
```

The architecture rule is:

```text
cross-note reasoning / recommendation / comparison
    -> generic Core retrieval + grounded synthesis

specialized executable behavior
    -> DelegateAction -> registered capability/app
```

A dedicated app is justified only when the request needs domain-specific executable semantics such as persistent workflow state, external side effects/integrations, specialized permissions, exact analytics/calculation contracts, or specialized mutation/lifecycle rules. Merely needing to reason across several notes is not enough.

The likely failure mode is retrieval, not reasoning: a whole-query embedding can recover one side of a comparison while missing another candidate set whose wording is only indirectly related. If real usage exposes that problem, test the smallest generic decomposition/candidate-set improvement before adding a reranker, graph database, vector database, agent framework, or new long-lived service.

Guardrails for this pattern:

- keep canonical note identity and provenance attached to every evidence item;
- distinguish retrieved fact from model inference/suggestion in output and future inspector views;
- never persist inferred relations automatically unless the user explicitly asks and normal write validation succeeds;
- prefer deterministic candidate filters when a domain later provides useful structured fields;
- fail gracefully when a required evidence set cannot be retrieved reliably.

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
