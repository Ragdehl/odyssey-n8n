# ADR 0006: Separate general knowledge context retrieval from identity retrieval

## Status

Accepted and implemented in Phase 13.

## Context

Odyssey needs to provide grounded notes to a future reasoning layer after a retrieval request has
already been interpreted. This is different from Phase 10 semantic candidate retrieval, which
only supplies evidence about which existing entity a reference might identify.

## Decision

Implement `get_context` with a separate disposable SQLite `ContextIndex`. The index embeds whole
validated atomic notes using the existing local embedding boundary and supports exact canonical
type filtering, all-of controlled-tag filtering, and schema-declared structured filters before
deterministic cosine ranking. The validated filters compile to parameterized SQLite predicates;
callers never supply SQL. Selected results are reread and validated from the Markdown vault, which
remains authoritative. Tags are included in the context projection and index but remain excluded
from identity retrieval and contextual-resolution provider evidence.

The V1 capability has no LLM, identity resolution, graph traversal, answer generation, automatic
refresh, threshold, chunking, or reranking. The schema registry marks filterable fields and
declares their value types and operators; registry changes require an explicit index rebuild.
Explicit rebuild and explicit caller `limit` keep the behavior deterministic and bounded at the
current vault scale.

## Consequences

The two retrieval contracts can evolve independently without changing accepted identity semantics.
The small amount of derived-index implementation duplication is preferable to coupling general
knowledge retrieval to identity resolution. A selected note whose source hash changed since
indexing fails closed until an explicit rebuild.
