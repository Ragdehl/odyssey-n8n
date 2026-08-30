# Phase 17E schema utility review

Status: **IN PROGRESS**

This document is the working decision record for the Phase 17E pre-E2E schema utility review defined in the canonical Functional Roadmap and governed by the Odyssey knowledge-model direction.

The review classifies each current canonical type and property as `KEEP`, `DEFER`, or `REMOVE` based primarily on direct user-visible value. No ontology/schema change is implied by documenting a review decision; actual schema changes still require explicit proposal, validation, and human approval.

## Review test

For each note type and property, ask separately:

```text
NOTE VALUE
Why does this thing deserve a stable note identity?

TYPE VALUE
What recurring user-visible behavior becomes possible because Odyssey knows what kind of thing it is?

PROPERTY VALUE
What deterministic filter, sort, comparison, calculation, reminder, automation, or application behavior becomes possible because the value is structured?
```

Structure is not justified merely because it saves LLM tokens or is easy to model.

## Schema ownership boundary

Odyssey Core owns the **mechanism** for registered schema, not the product meaning of every domain type.

```text
Odyssey Core
    |
    +--> registry / validation
    +--> safe create/update/delete
    +--> retrieval / links / history
    |
    `--> registered schema values
            |
            +--> Core-owned generic types
            +--> app/domain-owned types and properties
            `--> future explicit user-defined extensions
```

A domain application owns the semantics and user-facing behavior of the types/properties it contributes. Core should be able to validate, store, retrieve, mutate, link, and audit those values without implementing the application's business workflow.

Therefore Phase 17E should not force every current type to remain permanently Core-owned merely because it currently lives in the single canonical `note-schema.json`. Until a safe extension/registration mechanism exists, useful domain types may remain in the current registry as an implementation bridge.

When an application later proposes a type/property, the extension boundary should detect overlap with existing registered schema and prefer reuse when the proposed structure represents the same fundamental entity class. Roles or app-specific states should normally be properties rather than duplicate types. True new entity classes may be registered as domain-owned types through the future validated extension contract.

Detailed domain properties should generally be decided when the corresponding application is designed, rather than pre-modelled now. Phase 17E only needs to preserve clear ownership and avoid prematurely expanding Core ontology.

## Decisions so far

### `concept` — KEEP

**Ownership:** likely Core-owned generic type.

**Note value:** an abstract subject with stable identity can accumulate knowledge and links across contexts.

**Type value:** allows concept-only collections/retrieval and distinguishes abstract reusable subjects from projects, people, documents, tasks, and other entity classes.

**Type-specific properties:** none. Keep none for now; no concrete concept property currently unlocks enough user-facing behavior to justify extra schema.

**Risk to retain in validation:** `concept` must not become the planner's generic fallback whenever another type is uncertain. Existing planner benchmarks have exercised type discrimination; Phase 17E retrieval/planner validation should continue to include sentinel cases for overuse of `concept`.

### `project` — KEEP

**Ownership:** domain-owned in the future Projects/Tasks application; retained in the current registry until the extension boundary exists.

**Note value:** a project deserves persistent identity because decisions, ideas, tasks, documents, facts, and links can accumulate around the same initiative over time.

**Type value:** enables project-only views/retrieval and a stable project identity that later project-oriented applications or workflows can target.

**Type-specific properties:** none now. Project-specific fields such as `status`, `deadline`, `priority`, `owner`, or `progress` should be defined by the Projects/Tasks domain when that application is designed, then registered through Odyssey's schema boundary rather than becoming ad hoc frontmatter.

### `task` — KEEP

**Ownership:** domain-owned in the future Projects/Tasks application; retained in the current registry until the extension boundary exists.

**Note value:** an actionable item can deserve persistent identity when context, facts, documents, projects, dependencies, and later updates accumulate around the same action.

**Type value:** distinguishes actionable knowledge from ordinary facts/concepts and enables task-only views, retrieval, and later task application behavior.

**Type-specific properties:** none now. Expected future domain properties such as `status`, `due_date`, project membership, or parent/subtask relations should be designed with the Projects/Tasks application. Odyssey Core should supply the generic validated property/reference mechanism rather than owning task workflow semantics.

**Future schema capability to revisit:** relationships such as `project: [[Odyssey]]` or `parent_task: [[Another task]]` suggest a future typed entity-reference property contract. Do not add that contract during this review without the application use case and extension design.

## Type composition decision

### Multiple simultaneous canonical types — DEFER

Keep the current simple model:

```text
one canonical note
    |
    +--> one primary `type`
    |
    +--> optional controlled `subtype` only for a true stable specialization (`is-a`)
    |
    +--> properties for structured roles/relationships/state when they unlock user behavior
    |
    `--> tags/facts for cross-cutting or ordinary knowledge
```

Do **not** change `type` into an array or introduce multiple simultaneous canonical types now.

The primary type answers:

> What fundamental kind of entity is this?

A subtype, if later activated, should represent a genuine specialization of that parent type, for example a possible future `document -> invoice` relationship when the specialization unlocks useful behavior. The canonical schema already reserves an optional controlled `subtype`, but planner capabilities currently exclude it; Phase 17E does not activate subtype behavior merely because the field exists.

Roles or relationships should not be modeled as additional types when an existing structured property expresses them more directly. For example, a child remains `type: person`; if the relationship to the user matters for recurring filtering or behavior, `relationship_to_user: child` is the appropriate structure rather than a second `child` type.

Reconsider multi-type notes only after a concrete case demonstrates that **one stable identity genuinely needs the independent user-facing capabilities/property contracts of two canonical types at the same time**. At that point, evaluate composition conflicts explicitly, including required properties, incompatible type combinations, property-name collisions, migration semantics, and planner/retrieval complexity.

This keeps Odyssey from introducing ontology composition machinery before there is evidence that it solves a real user problem.

## Next review target

`store`
