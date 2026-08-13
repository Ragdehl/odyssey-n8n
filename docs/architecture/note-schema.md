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

## Generic metadata

Every note has these required generic fields:

- `id`: stable logical identity, independent of the filename and preserved across renames.
- `type`: controlled ID from the canonical type registry.
- `created_at`: note creation timestamp.
- `updated_at`: timestamp of the latest Odyssey modification.
- `created_by`: application or process that originally created the note.
- `updated_by`: application or process responsible for the latest modification.
- `revision`: positive integer incremented when Odyssey updates the note.
- `schema_version`: version of the note metadata/schema format.

The optional generic fields are:

- `subtype`: controlled subtype registered under the selected parent type.
- `aliases`: alternative names used for entity resolution; aliases do not create separate entities.

The schema deliberately adds no speculative universal or domain-specific metadata. Deterministic domain fields may be introduced later only when a demonstrated query or processing requirement justifies them.

## Controlled note types

The initial registry contains `concept`, `project`, `task`, `store`, `product`, `purchase`, `recipe`, and `document`. Each registry entry is a descriptive object with an ID, name, semantic boundary, illustrative examples, and a subtype registry. Examples explain intended use; they are not hard-coded entities.

`concept` is the fallback only when no more specific canonical type applies. A `purchase` is a human-readable occurrence note, while `product` identifies something reusable across purchases and `store` identifies the establishment. A `task` represents an action, but task lifecycle fields are outside this phase.

## Subtype policy

`subtype` is optional and is not arbitrary free text. When present, it must match a subtype registered under the note's selected parent type. The initial type definitions intentionally have empty subtype arrays because no demonstrated requirement currently justifies a subtype taxonomy.

Agents and workflows must not silently create canonical subtypes. Future subtype additions will use controlled schema evolution. The exact proposal, approval, and human-in-the-loop mechanism belongs to a later phase and is not implemented here.

## Relationships remain wikilinks

Ordinary Obsidian `[[wikilinks]]` are Odyssey's default relationship mechanism. The canonical schema has no relation registry and requires no typed edge such as `purchased_at` or `ingredient_of`. A purchase or recipe expresses useful relationships naturally in readable prose and links. Domain-specific structured fields remain possible later, but only for a demonstrated deterministic need.

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

# Compra [[Carrefour Balma]]

Compré [[Leche Lactel]] y [[Tomates]].
```

The links are readable and useful without a mandatory `store` field or typed relation.

## Validation and future evolution

Run the deterministic validator and its standard-library tests from the repository root:

```bash
python3 scripts/validate_note_schema.py
python3 -m unittest discover -s tests -v
```

The validator checks the schema structure, controlled-field semantics, stable ID syntax, uniqueness, and descriptive registry entries without external dependencies.

The top-level `schema_version` starts at `1`. A future schema change must be explicit, reviewed for compatibility and migration impact, documented when significant, and reflected in this version as appropriate. Human approval is normally required for ontology changes. Phase 2 establishes the controlled schema but does not implement schema-evolution or approval workflows.
