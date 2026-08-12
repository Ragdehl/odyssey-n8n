# Ontology Principles

## Knowledge model

Odyssey represents knowledge using four related concepts:

- **Entity:** something with its own identity, such as a person, place, organization, project, product, or concept.
- **Fact:** an assertion about an entity or other ontology object, ideally with enough provenance or context to assess and update it later.
- **Relation:** a typed connection between ontology objects, such as a purchase event occurring at a store.
- **Event:** something that happened at a time or over an interval and may involve entities, facts, and relations.

These are logical concepts. Their initial physical representation is Markdown, but the ontology must not assume permanently that every logical object maps one-to-one to a file.

## Atomic knowledge

Notes should be atomic or as small as practically useful: each note represents one identifiable entity, concept, idea, person, place, project, or similar item. A single input may therefore create several notes, enrich existing notes, and link them.

Atomic does not mean fragmenting information without purpose. A unit should be independently identifiable, reusable, linkable, and maintainable. Facts that only make sense as attributes of an entity can remain with that entity; a distinct concept with its own identity should be resolvable separately.

## Identity resolution

Before creating an entity, Odyssey follows:

```text
RESOLVE
   |
   v
 REUSE
   |
   v
 ENRICH
   |
   v
CREATE only if necessary
```

1. **Resolve:** search existing identifiers, names, aliases, metadata, and useful context.
2. **Reuse:** select an existing entity when the identity is sufficiently clear.
3. **Enrich:** add new valid facts or links without discarding established knowledge.
4. **Create:** create a new entity only when no existing entity is an adequate match.

This sequence is the primary defense against duplicates. Resolution must also preserve uncertainty: when two candidates cannot be distinguished safely, the workflow should report ambiguity instead of guessing.

## Schema and instances

Normal entity creation changes instance data. Adding a type or relation definition changes the ontology schema and has wider consequences. These operations must not be treated as equivalent.

Types and relations will be descriptive structures rather than bare string lists. They are expected to include stable identifiers, human-readable meaning, and constraints or examples where useful. The exact structure is deliberately deferred to a later design phase.

This phase does not define a final type catalog, relation catalog, validation language, or Markdown serialization format.

## Schema evolution

Agents and ordinary domain workflows must not silently invent ontology types or relations. Future schema-management primitives are expected to separate reading, proposing, and approving changes, conceptually:

```text
get_schema
    |
    v
propose_type / propose_relation
    |
    v
human review
    |
    v
approve_schema_change
```

Schema proposals should explain the observed need, alternatives considered, compatibility impact, and migration implications. Human-in-the-loop approval is the normal path because a schema change can affect every domain workflow, existing note, and future interpretation.

Significant accepted schema decisions should be documented. Routine creation or enrichment of entities does not require an architecture decision record.
