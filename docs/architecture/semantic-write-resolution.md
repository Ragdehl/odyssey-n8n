# Semantic WRITE identity and reference resolution

Status: **current WRITE contract layered on the Phase 15–17 planner/application foundations**

This note records the post-Reference-&-Relationship-v1 simplification of ordinary singular WRITE identity. Historical Phase 15/16 documents still describe why local reference indexes and pre-writer binding were introduced; they are not the current model-facing contract.

## Model/Core boundary

Luna interprets language. Core owns identity.

For each ordinary write Luna must preserve three things:

1. the semantic description of the entity that owns the new fact;
2. the new fact or mutation itself;
3. semantic descriptions of other entities mentioned by that fact and worth linking.

A target description such as `mi hijo al que le gusta el fútbol`, `la amiga con la que cené ayer`, an exact name, or another contextual identity phrase is a semantic query. Luna does not choose a stable Odyssey ID and does not count write-unit indexes.

The provider-facing reference shape is:

```text
KnowledgeReference
├─ mention
├─ role
└─ selection
   ├─ entity
   ├─ query
   ├─ type
   └─ filters
```

`target_index`, `self_target`, `link_scope`, and `relational_reference` are not provider fields inside a fact reference. The ordinary write target keeps the established full `SelectionCriteria` contract because direct self writes and bounded relational source writes still need those explicit semantics.

## Possessives are identity evidence, not self authority

First-person possessive wording does not by itself select the authenticated self note.

```text
Mi hijo al que le gusta el fútbol adora el chocolate.
```

means:

```text
target.query = "mi hijo al que le gusta el fútbol"
fact         = "Adora el chocolate."
```

It must not become `target.self_target=self`. `self` is reserved for facts whose actual subject is the authenticated user, for example `Axel y Denis son mis compañeros de trabajo`.

For singular WRITE, `relational_reference` may be a **candidate anchor** rather than the final identity decision. Its source-relative `reference` defines the bounded current relationship universe; `target.query` still preserves the user's complete description and may contain additional qualifiers. Core first grounds every relevant current relationship fact (including incoming backlinks), projects only identities actually linked by those facts, and then evaluates the full `target.query` only inside that grounded universe. The relationship can therefore narrow `mi hija a la que le gusta ver detectives de animales` to current children before the richer description selects one child. A global semantic candidate cannot enter that second-stage decision.

Bare singular relationship targets keep the established direct path. `complete_set` writes remain stricter: their relational reference must still describe the complete requested set rather than a qualified subset, because that path writes one shared source fact for the whole grounded set.

## Resolution

Core resolves a semantic target or reference against current canonical evidence:

```text
semantic query
  -> exact/local semantic candidates
  -> bounded current relationship evidence when useful
  -> contextual Luna selection over supplied candidates
  -> one canonical stable identity or abstention
```

The contextual model may select only IDs supplied by Core. No similarity score, possessive phrase, or planner field is itself mutation authority.

When a descriptive query carries a relational anchor, Core treats canonical structure and semantic interpretation as separate steps: relationship facts define the candidate universe; the full query chooses at most one member. Candidate evidence includes the canonical note body plus current incoming backlink facts, so information stored on another Note but linked to the candidate participates in identity resolution without copying knowledge or treating an index as authority. The same rule applies to `self` sources and named/existing sources such as `los amigos de Bruno`.

Known tombstoned link targets (`deleted: true`) are not current identities and therefore cannot enter or block a qualified singular relationship candidate set. Core keeps the containing fact inside the evidence guard, ignores only the inactive target for candidate narrowing, and still fails closed for malformed, ambiguous, or genuinely missing links whose identity state cannot be established. Complete-set semantics remain stricter and never treat a partial active subset as complete.

For qualified singular WRITE relationship anchoring, only the selector's supplied fact IDs carry relevance authority. They must be unique IDs from the exact Core-supplied batch. The reusable semantic-set response also contains character-span occurrence decorations, but those spans do not grant identity or mutation authority on this WRITE path and are not revalidated as relational proof; every chosen fact is instead re-read from canonical Markdown and its link targets are projected by Core before it can narrow candidates. This avoids making a harmless model span offset a false WRITE failure boundary while preserving the stricter occurrence checks on existing relational READ.

## Fact references

Provider references are lowered inside Core to the established deterministic reference-binding machinery. This lowering is an implementation bridge only: Luna never emits the local target indexes or lookup-only helper units.

A semantic fact reference first resolves against current canonical identities. If it resolves to exactly one existing note, Core binds that identity without mutating the referenced note. If no existing identity is found and the reference carries a canonical Odyssey note type, the normal WRITE creation contract may create that entity and then bind the new canonical path into the source fact. This is how a phrase such as `el proyecto Faro` can create a `project` note when `project` is a canonical schema type.

The active `note-schema` is the authority for that creation vocabulary. Core must not add a second hidden ontology such as a separate "concrete enough" test. Types whose semantics belong to future applications stay out of the active registry until those applications define them; an inactive type cannot silently become CREATE authority.

A new entity created only to satisfy a semantic fact reference is dependency-atomic with the fact that consumes it. Core may preflight and materialize dependencies first, but if no consuming source fact ultimately materializes, the just-created revision-1 helper is revalidated and rolled back before the request is committed or the derived index is refreshed. Independent successful branches may still remain `PARTIAL`; this is not whole-request transactional rollback.

If existing evidence is ambiguous, Core still defers for clarification rather than creating a duplicate or guessing. If unresolved reference wording has no canonical note type, Core has no creation authority; non-entity context should remain literal fact text rather than being promoted to a reference.

Legacy pre-existing index-based internal fixtures may retain their historical non-blocking pending behavior while migration is incomplete. That compatibility path must not re-enter the provider schema.

## Deferred ambiguity explanation

The current contextual resolver can safely return `RESOLVED`, `AMBIGUOUS`, or `UNRESOLVED`, but `AMBIGUOUS` does not yet carry the smaller set of candidates the model considered genuinely plausible. The application therefore cannot reliably explain a conflict such as "Cloe and Bruno Test both match this description" without risking presentation of unrelated candidates from the broader retrieval set.

A later focused change should let an ambiguous contextual decision return a validated subset of supplied `candidate_ids` together with enough grounded source evidence for a useful user-facing clarification. Core must verify every returned ID was in the supplied candidate set and must never manufacture the explanation from semantic rank alone. This is a model-facing contract change and requires its own deterministic fail-closed coverage and focused live gate; it is intentionally not part of the current atomicity/schema amendment.

## Required sentinels

The focused contract must keep deterministic coverage for at least:

- `Axel y Denis son mis compañeros de trabajo` — self is the subject; both coworkers are semantic fact references and participant notes are not reciprocally mutated;
- `Mi hijo al que le gusta el fútbol adora el chocolate` — use the child relationship as a bounded candidate anchor when available, preserve the full qualifier, and update the resolved child rather than self;
- `La amiga con la que cené ayer se muda a París` — resolve a contextually described target;
- `Mi hijo mayor fue al cine con la amiga que vive en Lyon` — relationally narrow the described child target, then resolve the described fact reference independently;
- `El amigo de Bruno que vive en Lyon se muda a Toulouse` — ground Bruno first, admit friend candidates from Bruno's outgoing facts or incoming backlinks, and apply the Lyon qualifier only inside that set;
- a genuinely ambiguous reference — defer for clarification without guessing, creating an identity, or writing a falsely settled source fact.

The provider-facing schema/prompt change requires focused live evidence under `AGENTS.md`. That live gate is Luna/low only, planner-only, zero retries, zero Sol fallbacks, cost-gated, non-overwriting, and separate from deterministic Core execution tests.

## Live-gate status

After integration with the collection/clarification contract, the five-case Luna/low planner gate ran at commit `1f0047d` under an explicitly authorized `$0.070515` conservative ceiling and `58,227`-byte input bound. All five frozen cases passed with five Luna/low calls, zero retries, zero Sol calls, and an estimated actual cost of `$0.0044110`. That evidence remains historical evidence for that exact model-facing contract.

A manual DEV regression then exposed a distinct planner/Core boundary: for `Mi hija a la que le gusta ver detectives de animales adora el chocolate`, Luna preserved the full `target.query` and also emitted `relational_reference = "mi hija"`, but Core treated the relationship as a terminal one-fact decision and deferred before using the richer qualifier. A temporary exact-wording guard proved that the qualifier itself resolves correctly, but the durable design is stronger: keep the relationship as grounded candidate authority and use the complete query as the second-stage discriminator. This also generalizes to named sources and incoming backlinks instead of falling back to a vault-wide semantic search.

A subsequent retry of that same event-participant case exposed a separate Core source-resolution leak: the planner was now valid, but Core resolved `relational_reference.source_query` using the full qualified target query as semantic context. The target-only qualifier `Airbus Test` therefore biased local source ranking toward Marta/Airbus instead of the intended `Cena relacional de prueba` anchor. Existing relationship sources are now resolved against the relationship anchor wording itself (`relational_reference.reference`), while the full target query is reserved for the second-stage member discriminator. This keeps anchor identification and member qualification as separate semantic decisions.

A later manual event-participant WRITE exposed a planner cardinality/source-placement boundary before Core execution. The request targeted one qualified participant from a multi-member relationship source. Both Luna and the normal Sol fallback produced locally invalid relational selection (`RELATIONAL_REFERENCE_CONFLICT`), so zero mutation occurred. The planner contract now makes the distinction explicit: `members=one` describes the final selected identity even when the anchor universe contains several members, `complete_set` is reserved for requests targeting the whole relationship set, and an `existing` anchor source belongs only in `relational_reference.source_query` while `target.entity` remains null. The exact manual phrase is a frozen case in the pending current-contract gate.

The pending active-schema gate therefore uses a distinct registry that preserves the historical v1 evidence while covering the exact daughter regression, a generic existing-source case (`El amigo de Bruno que vive en Lyon...`), and the manual event-participant regression (`De las personas que estuvieron en la cena relacional de prueba...`). It now contains seven Luna/low planner cases and preflights at a conservative no-cache ceiling of `$0.0941486` with a `54,961`-byte input bound. `MAX_COST_USD` remains `$0.00`; no provider call has been made for this amended contract and a fresh explicit authorization is required before running it.
