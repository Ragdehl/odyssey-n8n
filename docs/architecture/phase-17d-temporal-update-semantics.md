# Phase 17D temporal update semantics

Status: **current after Phase 17C and before the first real Phase 18 E2E**

## Objective

Distinguish a **correction of false knowledge** from a **real-world state transition** so Odyssey does not destroy information that was true in the past merely because a current fact or property changes.

The current bounded UPDATE writer can legitimately replace text such as `Marta trabaja en Airbus` when a later request says `Marta ahora trabaja en Thales`. That is appropriate only when the earlier statement was wrong. It is not the desired behavior when Marta really did work at Airbus and later changed employer.

The target semantics are:

```text
real-world transition

before
  current employer: Airbus

user
  "Marta ha dejado Airbus y ahora trabaja en Thales."

             |
             v

current state
  employer: Thales              # when employer is a registered property
  OR current body fact: Thales  # when no such property exists

canonical historical knowledge
  Marta trabajaba en Airbus.
  Ahora trabaja en Thales.
```

A registered current-state property remains useful for fast deterministic questions about the present, while the prior true fact remains queryable canonical knowledge rather than surviving only in Git history. When the active schema has no suitable property, Odyssey must preserve the same temporal meaning in the Markdown body instead of silently extending the ontology.

## Core distinction

Odyssey must preserve the semantic difference between these intents.

### Correction

The previous knowledge was false, duplicated, or should not remain part of the user's knowledge.

```text
"Me equivoqué: Marta nunca trabajó en Airbus; trabaja en Thales."
```

Expected direction:

```text
current state: Thales
Airbus claim removed/corrected
```

Explicit remove/delete requests remain valid removal authority subject to the existing safety rules.

### State transition

The previous knowledge was true, but the world changed.

```text
"Marta ha dejado Airbus y ahora trabaja en Thales."
"Marta ya no vive en Toulouse; ahora vive en Lyon."
```

Expected direction:

```text
current state    -> new current value
historical fact  -> preserve prior state and transition
```

A phrase such as `ahora`, `ya no`, `ha dejado`, `se mudó`, `empezó`, `terminó`, or equivalent contextual evidence may indicate a transition. Explicit correction language such as `me equivoqué`, `en realidad`, `nunca`, `era incorrecto`, or equivalent evidence may authorize destructive correction. The production planner/writer behavior must be evidenced before implementation.

When correction versus transition remains ambiguous, preserving prior knowledge is safer than destructive replacement. Odyssey may preserve both statements or defer when necessary, but it must not silently erase an earlier canonical claim merely because a new current claim was supplied.

## Why Git history is insufficient

Phase 17C provides audit and recovery history, but Git is not canonical user knowledge. A user should be able to ask questions such as:

```text
"¿Dónde trabajaba Marta antes de Thales?"
"¿Cuándo dejó Marta Airbus?"
"¿En qué ciudades ha vivido Marta?"
```

without requiring Odyssey to reconstruct domain knowledge from repository diffs.

Therefore a temporal transition must preserve appropriate historical knowledge in the Markdown source of truth.

## Structured current state plus historical knowledge

The smallest intended model is hybrid rather than full event sourcing:

```text
entity
  |
  +--> registered current structured properties, when available
  |
  `--> canonical facts/body containing relevant current and historical knowledge
```

Do not introduce a generic event store, temporal database, transaction framework, or history ontology merely to solve this requirement.

Some domains may later justify explicitly temporal structured properties, but ordinary personal knowledge should first use the smallest representation that preserves both:

1. the latest state needed for deterministic queries and applications when the schema already supports it;
2. past facts that remain meaningful knowledge.

### Schema availability rule

Phase 17D must not silently add properties merely because an example would benefit from them. In the current canonical schema, examples such as `employer` and `residence` are not registered `person` properties. They therefore remain body knowledge in this phase unless a separately approved schema change introduces those properties later.

The generic rule is:

```text
new temporal knowledge
        |
        +--> matching registered property exists
        |       -> update current property
        |       -> preserve meaningful history in body
        |
        `--> no matching registered property
                -> preserve prior + current temporal meaning in body
```

This keeps Phase 17D compatible with future schema extensions without making temporal preservation depend on any particular ontology field.

## Planner/writer contract direction

The first implementation must test the smallest existing contract before adding a new temporal discriminator to `KnowledgeUnit` or `PropertyChange`.

Today the planner normally omits a fact when a canonical property fully represents it. Phase 17D needs a narrow exception: when a correction or state transition requires reconciliation of existing body knowledge, the planner may preserve that semantic update in `facts` even when the new current value is also represented by a registered property.

Those facts must retain the correction/transition meaning supplied by the user rather than normalizing both cases into the same timeless statement. The bounded writer can then reconcile the authoritative body while deterministic property staging continues to own registered metadata changes.

Do **not** add a `temporal_mode`, generic event object, or other new structured planning field unless focused live evidence shows that the existing `facts` plus property-mutation channel cannot preserve the distinction reliably enough. Such a field would be a model-facing contract expansion and must be justified by evidence rather than convenience.

## Dates and temporal precision

Preserve temporal information when the user supplies it explicitly.

Examples:

```text
"Desde marzo Marta trabaja en Thales."
"Marta dejó Airbus el 12 de junio."
```

In the first implementation, temporal qualifiers belong in canonical knowledge/body facts unless an already-registered property explicitly owns that value. Phase 17D does not add generic `valid_from`, `valid_to`, transition-event, or temporal metadata fields.

A request timestamp may provide bounded context for expressions such as `hoy` or `ayer` only when the user's wording establishes that those expressions refer to the domain event. Odyssey must not fabricate an exact transition date merely because a request was received on a particular day. The word `ahora` establishes current-state semantics but does not by itself establish an exact transition date.

## Existing structured state without a matching body fact

When a future registered current-state property contains an old value but no corresponding historical body fact exists, a clear transition may preserve that old canonical value as history while applying the new current value. This is not invention: the old value was already canonical knowledge.

If the wording is ambiguous between correction and transition, do not convert the old property value into asserted history and do not destroy it as false merely by guessing. Preserve conservatively or defer according to the established request-level safety rules.

## Relationship to properties

This requirement reinforces rather than weakens the property model.

Properties should usually answer **what is true now** when the domain is naturally current-state oriented and the property is actually registered in the active schema:

```text
person.employer = Thales     # future example if registered
person.residence = Lyon      # future example if registered
```

Historical knowledge answers how that state evolved:

```text
previously worked at Airbus
previously lived in Toulouse
```

When those properties are absent from the active schema, the body carries both current and historical knowledge. This preserves the product goal that properties provide deterministic, cheap, application-friendly current state without forcing the user to maintain them manually, sacrificing meaningful past knowledge, or allowing the LLM to invent schema.

## Acceptance criteria

Before Phase 17D is complete, focused deterministic and live-model evidence should demonstrate at least:

1. A clear correction can remove/replace a false prior fact.
2. A clear state transition preserves the prior true state while representing the new current state.
3. `Marta trabaja en Airbus` -> `Marta ahora trabaja en Thales` is not treated as an unconditional destructive replacement.
4. Residence, employment, status, and similar representative temporal transitions are covered as body knowledge when no registered property exists.
5. The same contract remains compatible with registered current-state properties without adding schema fields in this phase.
6. Explicit user-supplied dates are preserved.
7. Missing dates do not gain invented precision.
8. Ambiguous correction-versus-transition wording fails closed or preserves information conservatively.
9. Existing identity, revision, reference-binding, schema-validation, pending-work, request-level Git history, and request-level safety rules remain intact.
10. No generic event-sourcing infrastructure is introduced.
11. Historical facts remain retrievable as canonical knowledge, not only through Git.

Because this changes production model-facing UPDATE semantics, the final implementation requires focused live evidence with the production planner/writer configuration plus proportional regression sentinels under `AGENTS.md`.

## Out of scope

- adding `employer`, `residence`, or another domain property solely for Phase 17D;
- a universal temporal ontology;
- storing every change as a first-class event entity;
- automatic exact-date inference without evidence;
- generic bitemporal/event-sourced storage;
- replacing Phase 17C Git audit history;
- user-facing timeline UI;
- analytics over arbitrary historical intervals;
- automatic migration of all existing notes before evidence establishes a representation.

## Open decisions for implementation

Focused live evidence must now answer only the remaining implementation questions:

1. whether the existing `facts` plus property-mutation channel preserves correction-versus-transition semantics reliably enough, or whether an explicit planner discriminator is actually required;
2. the smallest natural Markdown rendering the bounded writer reliably produces for preserved historical facts;
3. the proportional regression-sentinel set needed to protect existing ordinary append/correction/remove behavior.

The governing product rule is: **a new current truth must not erase an old truth merely because the world changed; destructive removal is for correction or explicit removal, not ordinary temporal evolution.**
