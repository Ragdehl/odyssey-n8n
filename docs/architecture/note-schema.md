# Canonical Note Schema

## Authority

The exact machine-readable Odyssey note schema is [`config/note-schema.json`](../../config/note-schema.json). This document explains its ownership and semantics without copying the full registry.

At this repository revision the active schema is **version 3**. Agents and applications must read the JSON for exact current fields, type IDs, constraints, retrieval guidance, and version rather than relying on a duplicated prose catalog.

```text
config/note-schema.json
        |
        +--> note validation
        +--> persistence/materialization
        +--> planner capability projection
        `--> deterministic retrieval filters
```

## Data ownership

| Data class | Canonical location | Meaning |
| --- | --- | --- |
| Application schema | Git: `config/note-schema.json` | Versioned field/type definitions and machine guidance |
| Personal knowledge | `/data/odyssey/vault` | Authoritative Markdown notes |
| Durable app/workflow state | `/data/odyssey/state` | Non-knowledge state such as pending work |
| Runtime data | `/data/odyssey/runtime` | Rebuildable indexes/caches/projections |

## Universal metadata

The current schema provides universal technical/identity/lifecycle fields including stable `id`, canonical human-readable `name`, controlled primary `type`, lifecycle timestamps, provenance, revision/version, optional aliases, optional soft-delete state, and optional tags.

Important semantics:

- `id` is stable logical identity and does not change on rename.
- `name` is the current canonical human-readable identity.
- the filename is a stable technical creation-time label and is not semantic identity;
- `revision` supports fail-closed optimistic concurrency;
- `schema_version` allows explicit compatibility/migration handling;
- `deleted: true` is Core-managed recoverable soft deletion; absence represents normal active knowledge;
- `aliases` are alternate names for the same identity and are not inferred automatically from arbitrary mentions;
- `tags` are explicit free-form user/app facets. Core has **no built-in semantic tag vocabulary**.

The active schema has no general `subtype` field. Do not reintroduce subtype behavior merely because older historical documents/fixtures mention it.

## Provenance

`created_by` and `updated_by` are named provenance objects rather than scalar actor strings:

```yaml
created_by:
  human: <stable-user-id-or-null>
  app: <stable-app-id-or-null>
```

At least one of `human` or `app` must be present. The human is the originator/intent source when applicable; the app identifies the executing/originating application/capability. Provenance is not itself the future authorization model.

Legacy scalar actors may be normalized only at explicitly supported bounded persistence inputs; new canonical notes follow the active schema.

## Note types and properties

`type` is one controlled primary type selected from the registry in `config/note-schema.json`. Core owns the registry/validation mechanism; the product semantics of some registered types may later belong to applications/domains.

Do not duplicate the active type list here. The JSON is the single catalog. The current minimal Core philosophy is:

- types distinguish reusable fundamental knowledge classes when that distinction unlocks behavior;
- type-specific properties are sparse;
- a property exists for deterministic filtering, sorting, comparison, calculation, reminder, automation, or application behavior—not merely because a fact can be structured;
- roles/relationships should not become extra simultaneous types when a property/link can express them more directly.

The active schema currently retains `journal_entry.entry_date` as a required domain date for journal entries. It is distinct from `created_at`: `entry_date` is the date the entry describes, while `created_at` is when Odyssey created/stored the note.

## Relationships

Ordinary Obsidian `[[wikilinks]]` remain the default relationship representation. The schema has no required generic relation registry or typed-edge graph. Add a structured relation/property only when a demonstrated deterministic behavior requires its role.

## Tags

Tags are deliberately simple:

```text
Core
  -> stores explicit values
  -> validates basic shape
  -> applies explicit add/remove
  -> supports exact membership filtering
  -> does not own vocabulary or semantic inference

User/application
  -> chooses values
  -> owns their meaning/policy
```

Historical Phase 14–16 documents may refer to the earlier controlled tag registry; Phase 17E removed that Core-owned vocabulary. The active JSON and [Phase 17E common metadata review](phase-17e-metadata-review.md) are authoritative for the current direction.

## Validation and evolution

From the repository root, the canonical deterministic checks include:

```bash
python3 scripts/validate_note_schema.py
pytest
```

`odyssey_core.notes.validate_note` validates note instances against an explicitly supplied parsed schema. Schema-definition validation checks the registry itself. Persistence additionally enforces lifecycle/revision/identity rules at the appropriate boundary.

A schema change is a product/architecture change, not ordinary note creation. It must be explicit, reviewed for compatibility/migration impact, deterministically validated, and normally human approved. Applications or models must never silently add unregistered canonical metadata.

For the broader modeling rule, see [Odyssey Knowledge Model](knowledge-model-direction.md).
