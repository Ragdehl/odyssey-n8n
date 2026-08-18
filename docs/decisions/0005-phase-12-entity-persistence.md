# 0005: Phase 12 entity persistence

Status: Accepted

## Context

Odyssey needs a deterministic Core boundary for writing an already-decided entity state. Identity
resolution and future interpretation must remain separate from persistence, and a failure to find
an entity must not silently authorize creation.

## Decision

Phase 12 retires the roadmap name `upsert_entity` and exposes explicit `create_entity` and
`update_entity` operations. `UNRESOLVED != CREATE`: the caller must choose creation explicitly.

Properties and body content are persisted here when supplied as structured, already-decided
mutations; they are not inferred. Core owns lifecycle fields. Create assigns the supplied stable ID,
current schema version, timestamps, actor, and revision 1. Update preserves ID, creation metadata,
and schema version; it increments revision and refreshes update metadata only for a real change.
Lifecycle fields are protected from caller mutation. Updates are explicit property patches or exact
body replacement, never a smart Markdown merge. A no-op does not write or create a revision.

Stable IDs must be unique among validated canonical vault notes. Updates require both a physical path
and matching `expected_id`, so stale paths fail closed. `VaultRepository` remains the only normal
vault filesystem boundary and gains only the contained atomic replacement primitive required by
updates.

Phase 12 has no LLM or provider dependency. Future Phase 14 decides meaning, and future Phase 15
orchestrates persistence and canonical wikilinks; neither responsibility is implemented here.

## Consequences

Callers must provide stable IDs, lifecycle timestamps, actors, and explicit domain changes. The
simple duplicate-ID scan is correct for the current vault scale; a derived index can be considered
later without changing the source-of-truth boundary. Explicit create/update semantics make
unresolved identity safe but require later orchestration to make the creation decision deliberately.
