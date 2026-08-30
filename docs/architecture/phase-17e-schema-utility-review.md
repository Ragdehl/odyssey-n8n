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

## Decisions so far

### `concept` — KEEP

**Note value:** an abstract subject with stable identity can accumulate knowledge and links across contexts.

**Type value:** allows concept-only collections/retrieval and distinguishes abstract reusable subjects from projects, people, documents, tasks, and other entity classes.

**Type-specific properties:** none. Keep none for now; no concrete concept property currently unlocks enough user-facing behavior to justify extra schema.

**Risk to retain in validation:** `concept` must not become the planner's generic fallback whenever another type is uncertain. Existing planner benchmarks have exercised type discrimination; Phase 17E retrieval/planner validation should continue to include sentinel cases for overuse of `concept`.

### `project` — KEEP

**Note value:** a project deserves persistent identity because decisions, ideas, tasks, documents, facts, and links can accumulate around the same initiative over time.

**Type value:** enables project-only views/retrieval and a stable project identity that later project-oriented applications or workflows can target.

**Type-specific properties:** none. Keep none in Core for now. Fields such as `status`, `deadline`, `priority`, `owner`, or `progress` should be introduced only when a concrete recurring user capability demonstrates that they belong in canonical Odyssey knowledge rather than in a project application/domain layer.

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

`task`
