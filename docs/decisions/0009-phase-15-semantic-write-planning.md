# ADR 0009: Phase 15 semantic write-planning boundary

- Status: Accepted for deterministic preparation; Sol/low experiment pending
- Date: 2026-08-21

## Context

Phase 14's `CreateNoteAction` deliberately retained raw user content for a later preparation layer.
Phase 15 needs that preparation while preserving Phase 12's rule that missing identity does not
authorize creation. A second interpretation call would duplicate request understanding, cost, and
latency without a demonstrated benefit.

## Decision

Replace `CreateNoteAction` with semantic `WriteAction` in the evolved RequestPlan contract. One
Sol/low call may emit ordered existing `RetrieveAction` values and one or more `WriteAction` values.
Each write action contains grouped semantic knowledge units, not physical note instructions. The
minimal controlled intent vocabulary is `record`, `amend`, `remove`, and `delete`.

`record` expresses remembered knowledge but no physical create decision. It normally carries facts,
but may be factless only when another unit in the same action references it. `amend` and `remove`
require concrete facts; `delete` permits empty facts and must not create filler deletion text. `amend`,
`remove`, and `delete` explicitly require an existing target later and can never imply fallback
creation. Units may use canonical types where directly appropriate and can refer to another unit
through an in-plan index and semantic role. Grouping applies only to facts with the same subject and
compatible intent; different intents remain separate units. The planner has no identity, path, ID,
Markdown, SQLite, repository-existence, or persistence authority.

## Alternatives considered

- Keep `CreateNoteAction`: rejected because its physical name incorrectly suggests a creation
  decision and cannot express correction/removal/deletion intent.
- Add a separate write-planning call: rejected absent evidence that one Sol/low structured response
  cannot safely cover both planning responsibilities.
- Add a broad operation or relationship taxonomy: rejected because the four concrete user intents and
  free-text reference roles cover the demonstrated cases without silently changing ontology.

## Consequences

Phase 14 retrieval actions and Phase 13 `get_context` remain unchanged. Phase 15 validates but does
not execute plans. The planned benchmark must establish Sol/low quality before the evolved production
prompt is used for paid traffic. Identity resolution and explicit persistence remain Phase 16 work,
including the enduring `UNRESOLVED != CREATE` rule.
