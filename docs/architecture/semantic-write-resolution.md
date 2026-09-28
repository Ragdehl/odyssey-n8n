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

When a descriptive query starts from an authenticated-self relationship, Core may expose bounded one-hop canonical relationship evidence and related current identities to the contextual resolver. This expansion supplies evidence only; it never selects the target automatically.

## Fact references

Provider references are lowered inside Core to the established deterministic reference-binding machinery. This lowering is an implementation bridge only: Luna never emits the local target indexes or lookup-only helper units.

A semantic fact reference is existing-identity-only unless the same request contains an independently authorized material unit for that entity. An unmatched reference lookup cannot create a new note merely because the mention exists in user text.

If a semantic reference resolves to exactly one existing note, Core binds the canonical path and materializes the wikilink before writing the source fact. If it is ambiguous or unresolved, the new semantic-reference source fact is deferred and the candidate evidence remains pending for clarification; Core neither guesses a link nor persists the source fact as if the reference were settled.

Legacy pre-existing index-based internal fixtures may retain their historical non-blocking pending behavior while migration is incomplete. That compatibility path must not re-enter the provider schema.

## Required sentinels

The focused contract must keep deterministic coverage for at least:

- `Axel y Denis son mis compañeros de trabajo` — self is the subject; both coworkers are semantic fact references and participant notes are not reciprocally mutated;
- `Mi hijo al que le gusta el fútbol adora el chocolate` — resolve the described child and update that child, not self;
- `La amiga con la que cené ayer se muda a París` — resolve a contextually described target;
- `Mi hijo mayor fue al cine con la amiga que vive en Lyon` — resolve both the described target and the described fact reference;
- a genuinely ambiguous reference — defer for clarification without guessing, creating an identity, or writing a falsely settled source fact.

The provider-facing schema/prompt change requires focused live evidence under `AGENTS.md`. That live gate is Luna/low only, planner-only, zero retries, zero Sol fallbacks, cost-gated, non-overwriting, and separate from deterministic Core execution tests.
