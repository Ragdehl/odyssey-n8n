# Canonical Note Schema

## Purpose and ownership

Odyssey's canonical note schema defines the generic metadata contract and controlled note types used by its human-first Markdown notes. Its machine-readable source of truth is [`config/note-schema.json`](../../config/note-schema.json).

JSON is used because n8n and JavaScript can consume it directly, it needs no YAML parser dependency, deterministic validation is straightforward, and GitHub presents clear diffs. The schema is version-controlled application configuration, so it belongs in Git with the code and architecture that interpret it.

The source-of-truth boundaries are:

| Data class | Canonical location | Responsibility |
| --- | --- | --- |
| Application schema | Git repository: `config/note-schema.json` | Versioned note metadata and type definitions |
| Personal knowledge | `/data/odyssey/vault` | Authoritative personal Markdown notes |
| Runtime data | `/data/odyssey/runtime` | Rebuildable indexes, caches, and derived state |

Phase 2 does not copy the schema to `/data/odyssey/config`, add a Docker mount, or decide how n8n obtains it. That runtime boundary will be chosen when a workflow demonstrates the need.

## Universal metadata and type-specific properties

Universal metadata supplies the technical fields shared by every note, such as stable identity, controlled type, revision information, and provenance. Type-specific properties hold deterministic domain information that belongs only to one note type. The exact field IDs, requirements, descriptions, and constraints for both are defined only in [`config/note-schema.json`](../../config/note-schema.json).

Every type definition has `id`, `name`, `description`, `examples`, `subtypes`, and `properties`. `properties` is always an array, including when empty. Each property is a lightweight definition with a stable `id`, non-empty `value_type`, boolean `required` marker, non-empty `description`, and optional `filterable` flag. The same flag on universal metadata fields tells deterministic context retrieval which fields may be constrained. This is intentionally not a general property language or JSON Schema system.

A possible property is not automatically a property Odyssey should add. Structured properties are introduced only for a demonstrated deterministic query or processing requirement. Otherwise, Markdown and wikilinks remain the clearer human-first representation.

## Controlled note types

Each registry entry defines a note type's semantic boundary without duplicating the complete canonical catalog in documentation. Consult [`config/note-schema.json`](../../config/note-schema.json) for the current registry. Examples in type definitions explain intended use; they are not hard-coded entities.

Two personal-knowledge boundaries are worth clarifying. A `person` gives an individual reusable identity so journal entries, projects, documents, tasks, and other notes can link to the same person. Its initial structured properties are deliberately limited to demonstrated personal use. A `journal_entry` represents a diary entry about a day, experience, reflection, or occurrence.

The journal entry's `entry_date` is distinct from universal creation metadata: it records the day described, while `created_at` records when Odyssey created the note. For example, an entry about 2026-08-13 may be written on 2026-08-14.

A general `event` type is intentionally deferred. An occurrence such as “Dinner with [[Carlos]]” belongs naturally in a journal entry and does not need a second entity. An event type may become justified later when an occurrence needs reusable identity across several notes or applications—for example, `[[Trip to Madrid August 2026]]` linked from journal entries, expenses, people, photos, and tasks.

## Subtype policy

`subtype` is optional and is not arbitrary free text. When present, it must match a subtype registered under the note's selected parent type. The initial type definitions intentionally have empty subtype arrays because no demonstrated requirement currently justifies a subtype taxonomy.

Agents and workflows must not silently create canonical subtypes. Future subtype additions will use controlled schema evolution. The exact proposal, approval, and human-in-the-loop mechanism belongs to a later phase and is not implemented here.

## Relationships remain wikilinks

Ordinary Obsidian `[[wikilinks]]` are Odyssey's default relationship mechanism. The canonical schema has no relation registry and requires no typed edge such as `purchased_at` or `ingredient_of`. A purchase or recipe expresses useful relationships naturally in readable prose and links. Domain-specific structured fields remain possible later, but only for a demonstrated deterministic need.

Journal entries use the same approach: people, projects, places, and concepts are ordinary wikilinks. Odyssey does not add relationship fields such as `met_person`, `discussed_project`, or `visited_store` merely to label those links.

For example:

```markdown
---
id: <stable-id>
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

The links are readable and useful without a mandatory `store` field or typed relation.

## Controlled tags

Tags are optional, lightweight cross-cutting facets for classification and later knowledge retrieval. They are not note types, precise domain properties, task status, identity evidence, or replacements for wikilinks. A type says what a note is; a property records a structured fact; a wikilink expresses a relationship; a tag adds a transversal facet.

The controlled-but-extensible initial vocabulary is: `idea` (possible proposal not yet a decision), `decision` (choice already made), `question` (open question worth retaining), `reflection` (observation, reasoning, interpretation, or conclusion), `reference` (knowledge kept for consultation), `hypothesis` (unestablished explanation or proposition), `explore` (marked for investigation), `someday` (possibility without current commitment or date), and `review` (knowledge worth revisiting). Their canonical descriptions in `config/note-schema.json` constrain use. Callers and LLMs must not invent tag IDs; adding one requires an intentional schema change. No mutual-exclusion rules apply yet.

Tags are intentionally excluded from semantic identity retrieval text and contextual provider evidence. Phase 13 uses them in broader context retrieval, including the existing all-of required-tag filter, but adds no tag inference, synonyms, weighting, or auto-tagging.

## Validation and future evolution

Run the deterministic validator and its standard-library tests from the repository root:

```bash
python3 scripts/validate_note_schema.py
pytest
```

The schema-definition validator checks the schema structure, controlled-field semantics, stable ID syntax, uniqueness, and descriptive registry entries without external dependencies. Separately, `odyssey_core.notes.validate_note` validates one generic note against an explicitly supplied parsed schema: required and allowed fields, controlled type and subtype, declared value constraints, type-specific properties, and compatible `schema_version`. It does not load a repository path or attempt historical lifecycle checks such as whether identity and revision stayed stable across earlier versions.

The top-level `schema_version` starts at `1`. A future schema change must be explicit, reviewed for compatibility and migration impact, documented when significant, and reflected in this version as appropriate. Human approval is normally required for ontology changes. Phase 2 establishes the controlled schema but does not implement schema-evolution or approval workflows.
