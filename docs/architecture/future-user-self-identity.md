# Future user self-identity binding

Status: **preserved near-term product/architecture direction; not yet implemented**.

## Goal

Odyssey should know which canonical `person` note represents the authenticated/current human user, so first-person requests and applications can reuse the user's own knowledge without creating a separate profile store or special note type.

The user's own note remains ordinary canonical personal knowledge in the main vault:

```text
current/authenticated user
        |
        | stable binding
        v
canonical person note in /data/odyssey/vault
        |
        +--> appears in normal search/retrieval
        +--> participates in links and statistics
        +--> accumulates ordinary facts about the user
        `--> can be viewed/edited/deleted through the same knowledge rules as other person notes
```

For example, if the user says:

```text
Me llamo Edgar, soy data engineer y trabajo en Alten para Airbus.
```

Odyssey may create or enrich an ordinary `person` note for Edgar. Once that note is safely identified as the current user's person identity, later requests such as `¿Dónde trabajo?`, `apunta que mi coche es un Scénic`, or an application needing facts about the current user can resolve first-person references against that same canonical note.

## Core distinction

Do not conflate **the actor using Odyssey** with **the canonical person entity that represents that human in personal knowledge**.

```text
request actor identity
        |
        +--> who initiated/executed the request
        |    e.g. created_by.human
        |
        `--> self-person binding
             e.g. current user -> stable person_note_id
                         |
                         v
                  canonical Person note
```

`created_by.human` and the self-person binding are related but distinct:

- `created_by.human` / `updated_by.human` record provenance: which human originated an action;
- the self-person binding says which canonical `person` note represents that human inside the knowledge graph/vault.

This separation should remain valid when Odyssey becomes multi-user.

## Storage direction

The **person note stays in the ordinary canonical vault** alongside every other note. It must not be moved into a private profile silo merely because it represents the current user.

The small binding itself is account/application identity state, not personal knowledge content. Conceptually:

```text
stable_user_id -> stable_person_note_id
```

The exact persistence mechanism is deferred, but it should live in the smallest durable user/account/authorization state that owns authenticated identity rather than as an ad-hoc fact inside the note body.

The binding must reference the canonical note by stable note ID, not by filename or mutable display name.

## Why not a special canonical field or type

Do not introduce a new `user` note type merely for self-identity. The user is still a person, and ordinary `person` semantics already provide the correct knowledge behavior.

Do not make `is_me: true` on the note the primary identity mechanism. That would mix account identity with knowledge content and becomes awkward under multi-user/shared knowledge.

Do not add `yo`, `me`, `mi`, or language-specific first-person words as aliases. First-person meaning depends on the current actor/session, not on the entity's canonical aliases.

A future UI may visually identify the user's own note (for example `Edgar · Tú`) by projecting the binding, without changing the note's ordinary canonical semantics.

## Planner/resolver behavior

Once implemented, the request boundary should supply the current actor/self binding as safe deterministic context. First-person references should resolve to the bound canonical `person` note before ordinary semantic identity search when the reference unambiguously denotes the current user.

Examples:

```text
¿Dónde trabajo?
-> target = current user's person note

Apunta que vivo en Toulouse.
-> add knowledge to current user's person note

Mi hermano vive en Madrid.
-> `mi` establishes relation to the current user, but the target is not automatically the user's own note
```

The planner/model should not infer who the current user is from names, recent chat text, or semantic similarity when a deterministic binding exists.

If no self-person binding exists yet, Odyssey must not silently guess. The first explicit self-identifying capture can provide evidence to create/select a `person` note, but establishing the durable binding should be an explicit, validated identity action with safe ambiguity handling.

## Applications

Applications/capabilities should receive or resolve the current user through the same generic identity boundary rather than maintaining their own user profile copies.

```text
Food app / Tasks / Projects / Help / future app
                 |
                 v
        current user binding
                 |
                 v
        canonical person note
                 |
                 v
       shared Odyssey knowledge
```

This keeps user knowledge reusable across applications and prevents per-app profile silos.

Application-specific settings or preferences that are not personal knowledge may still belong to application/account state; ordinary facts about the human belong to the canonical person note when they meet Odyssey's normal knowledge rules.

## Search, statistics, deletion, and visibility

Because the user's note is ordinary canonical knowledge:

- it participates in ordinary retrieval/search;
- it can appear in statistics/analytics that operate over canonical notes;
- it can link to and be linked from other canonical notes;
- user-facing Notes/Activity views should treat it like any other person note, with optional `Tú` presentation derived from the binding;
- deleting or changing personal facts should use the same canonical mutation/history rules as other notes.

If the user deletes the person note itself, the binding must not silently point to a missing/replacement identity. The implementation must fail safely and require rebinding or explicit recreation rather than guessing another person.

## Multi-user direction

The design should scale naturally:

```text
user A -> person note A
user B -> person note B
user C -> person note C
```

A shared canonical person note may be visible to multiple authorized users, but each authenticated actor has its own self binding. Authorization must be checked before retrieval/mutation; the binding itself must not grant access to knowledge that the actor is not otherwise allowed to access.

This also keeps shared knowledge semantics independent from self identity: `who am I?` is an account/actor binding question, while `what does Odyssey know about this person?` is a canonical knowledge question.

## Near-term implementation sequence

This is intentionally small and should be considered soon after production/development isolation, before substantial application work:

```text
production/development isolation
        |
        v
validate first real user's person note
        |
        v
persist stable user -> person_note_id binding
        |
        v
first-person resolver/planner context
        |
        v
focused deterministic/live validation
        |
        v
reuse across conversations and applications
```

No new vector service, profile database, special person schema, or dedicated model layer is required merely to support self identity.

## Validation scenarios

At minimum, implementation should cover:

- explicit self-identification creates or safely reuses one canonical `person` note;
- `¿Dónde trabajo?` resolves deterministically to the bound self note;
- `mi coche`, `mi casa`, `mi proyecto`, etc. use self identity without confusing the target entity;
- another person's statement does not accidentally update the self note;
- rename of the person note does not break the binding because stable note ID is used;
- deletion of the bound person note fails safely and does not rebind by similarity;
- two users with similar/same names retain distinct actor bindings;
- applications reuse the same binding instead of creating private profile copies;
- self-note facts remain searchable/statistically visible like ordinary canonical knowledge;
- no first-person alias hacks or hidden profile copy become a second authority.
