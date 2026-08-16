# Ontology Principles

## Knowledge model

Odyssey uses a lightweight ontology based on typed notes rather than an obligatory typed-edge graph. Its core principle is:

```text
Markdown / Obsidian
    =
simple human-readable notes
+ stable identity
+ note type
+ ordinary [[wikilinks]]
```

Each note or entity has stable identity, a controlled note type, human-readable content, and optional wikilinks to related notes. Notes form a lightweight graph through wikilinks and backlinks. The linked nodes are typed; the edges are untyped by default.

A wikilink plus the target note's type does not always encode the exact semantic meaning of a relationship. That limitation is acceptable in V1. If a concrete future query or process requires a semantic role to be deterministic, Odyssey may introduce the minimum necessary structured property at that time. Those properties are not designed in advance.

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

## Relationships and structure

Relationships are represented by ordinary Obsidian wikilinks by default. A purchase note can therefore say:

```markdown
---
id: purchase_2026_08_13_001
type: purchase
created_at: 2026-08-13T10:00:00+02:00
updated_at: 2026-08-13T10:00:00+02:00
created_by: n8n
updated_by: n8n
revision: 1
schema_version: 1
---

# Purchase at [[Carrefour Balma]]

I bought [[Lactel Milk]] and [[Tomatoes]].
```

If the linked notes have types `store` and `product`, they already provide machine-readable node type information. This is preferred over adding a `store: "[[Carrefour Balma]]"` property when that property solves no demonstrated query or processing requirement. Odyssey does not require every link to also carry a generic `relation_type` and target, and V1 has no predefined generic relation vocabulary.

Domain-specific frontmatter properties are not forbidden, but they are introduced only to satisfy a demonstrated requirement for deterministic structured querying or processing:

```text
human-readable link/content first
        |
        v
real deterministic requirement appears
        |
        v
add the minimum necessary structure
```

A future rebuildable index may infer machine-oriented relationships from source and target note types, wikilink position or context, text, and optional frontmatter properties. Such inference is optional machine enrichment; Markdown and Obsidian remain the human-first source representation.

## Frontmatter philosophy

Initial frontmatter combines universal technical metadata with the minimum type-specific properties justified by deterministic processing needs. The exact canonical definitions live only in [`config/note-schema.json`](../../config/note-schema.json); [Canonical Note Schema](note-schema.md) explains how to interpret them.

A property being possible does not mean Odyssey should add it now. Markdown content and wikilinks remain the preferred human-first representation when a fact does not need deterministic structure.

## Schema and instances

Normal note creation changes instance data. Adding a canonical note type changes the ontology schema and has wider consequences. These operations must not be treated as equivalent.

Canonical note types are descriptive schema objects rather than a bare string list. Each definition describes its identity and purpose, illustrative examples, controlled subtypes, and any justified type-specific properties. The registry is defined in [`config/note-schema.json`](../../config/note-schema.json). V1 does not have a global typed-relation schema.

## Schema evolution

Agents and ordinary domain workflows must not silently invent canonical note types. Future type-management primitives may separate reading, proposing, and approving changes, conceptually:

```text
get_schema
    |
    v
propose_type
    |
    v
human review
    |
    v
approve_type
```

Type proposals should explain the observed need, alternatives considered, compatibility impact, and migration implications. Human-in-the-loop approval is the normal path because a type change can affect domain workflows, existing notes, and future interpretation. These management operations are conceptual and are not implemented in Phase 2.

Significant accepted schema decisions should be documented. Routine creation or enrichment of entities does not require an architecture decision record.
