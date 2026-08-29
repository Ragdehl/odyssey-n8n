# Phase 17D temporal update semantics

Status: **planned after Phase 17C and before the first real Phase 18 E2E**

## Objective

Distinguish a **correction of false knowledge** from a **real-world state transition** so Odyssey does not destroy information that was true in the past merely because a current property changes.

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

current structured state
  employer: Thales

canonical historical knowledge
  Marta trabajaba en Airbus.
  Ahora trabaja en Thales.
```

The current property remains useful for fast deterministic questions about the present, while the prior true fact remains queryable canonical knowledge rather than surviving only in Git history.

## Core distinction

Odyssey must preserve the semantic difference between these intents.

### Correction

The previous knowledge was false, duplicated, or should not remain part of the user's knowledge.

```text
"Me equivoqué: Marta nunca trabajó en Airbus; trabaja en Thales."
```

Expected direction:

```text
current employer: Thales
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
current property -> new current value
historical fact  -> preserve prior state and transition
```

A phrase such as `ahora`, `ya no`, `ha dejado`, `se mudó`, `empezó`, `terminó`, or equivalent contextual evidence may indicate a transition, but the exact planner/writer contract must be evidenced before implementation. Ambiguity must fail closed rather than silently converting past truth into an error correction.

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
  +--> current structured properties
  |
  `--> canonical facts/body containing relevant history
```

Do not introduce a generic event store, temporal database, transaction framework, or history ontology merely to solve this requirement.

Some domains may later justify explicitly temporal structured properties, but ordinary personal knowledge should first use the smallest representation that preserves both:

1. the latest state needed for deterministic queries and applications;
2. past facts that remain meaningful knowledge.

## Dates and temporal precision

Preserve temporal information when the user supplies it explicitly.

Examples:

```text
"Desde marzo Marta trabaja en Thales."
"Marta dejó Airbus el 12 de junio."
```

The implementation contract must decide how to represent those dates without inventing unsupported precision.

A request timestamp may provide bounded context for expressions such as `hoy`, `ayer`, or `ahora`, but Odyssey must not fabricate an exact transition date merely because a request was received on a particular day when the user did not actually establish that the change happened then.

## Relationship to properties

This requirement reinforces rather than weakens the property model.

Properties should usually answer **what is true now** when the domain is naturally current-state oriented:

```text
person.employer = Thales
person.residence = Lyon
```

Historical knowledge answers how that state evolved:

```text
previously worked at Airbus
previously lived in Toulouse
```

This preserves the product goal that properties provide deterministic, cheap, application-friendly current state without forcing the user to maintain them manually or sacrificing meaningful past knowledge.

## Acceptance criteria for the future implementation

Before Phase 17D is complete, focused deterministic and live-model evidence should demonstrate at least:

1. A clear correction can remove/replace a false prior fact.
2. A clear state transition updates the current property without losing the prior true state.
3. `Marta trabaja en Airbus` -> `Marta ahora trabaja en Thales` is not treated as an unconditional destructive replacement.
4. Residence, employment, status, and similar representative temporal transitions are covered.
5. Explicit user-supplied dates are preserved.
6. Missing dates do not gain invented precision.
7. Ambiguous correction-versus-transition wording fails closed or preserves information conservatively.
8. Existing identity, revision, reference-binding, schema-validation, pending-work, and request-level safety rules remain intact.
9. No generic event-sourcing infrastructure is introduced.
10. Historical facts remain retrievable as canonical knowledge, not only through Git.

Because this changes production model-facing UPDATE semantics, the final implementation requires focused live evidence with the production planner/writer configuration plus proportional regression sentinels under `AGENTS.md`.

## Out of scope

- a universal temporal ontology;
- storing every change as a first-class event entity;
- automatic exact-date inference without evidence;
- generic bitemporal/event-sourced storage;
- replacing Phase 17C Git audit history;
- user-facing timeline UI;
- analytics over arbitrary historical intervals;
- automatic migration of all existing notes before evidence establishes a representation.

## Open decisions for implementation

Resolve these immediately before implementation from current code and focused examples:

1. whether correction-versus-transition intent belongs explicitly in the planner contract or can be represented safely by existing fact operations;
2. the smallest canonical Markdown rendering for preserved historical facts;
3. whether any current-state properties need explicit temporal metadata in the first implementation;
4. how request timestamps may ground relative expressions without inventing dates;
5. how to handle a new current value when the previous property value exists but no matching historical body fact is present;
6. what conservative behavior to use when the model cannot confidently distinguish correction from transition.

The governing product rule is: **a new current truth must not erase an old truth merely because the world changed; destructive removal is for correction or explicit removal, not ordinary temporal evolution.**
