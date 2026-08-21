# Phase 14 RequestPlan benchmark v3 — READY FOR HUMAN REVIEW

This separate, frozen-before-calls v3 experiment preserves v2.2 evidence unchanged. It prepares exactly two future stages, neither executed here: Terra/low for 24 cases and, after human review, Sol/low for the identical frozen inputs.

## Contract

`RequestPlan` has ordered `RetrieveAction` and `CreateNoteAction` values plus limitation codes. A v3 retrieval plan is exactly `{query, type, filters}`. Tags, canonical tag values, and subtype capability are intentionally absent from the planner contract. `type` and filters are recall-sensitive hard restrictions, so semantic facets remain in `query` unless the schema makes an explicit, safe mapping possible.

The stable cacheable prompt prefix contains the concise planner rules and a compact JSON capability projection derived from `config/note-schema.json`. The runner uses `odyssey-phase14-request-plan-v3`, records provider cache counters, and preserves append-only evidence. A received but malformed or invalid model output is a `success: true`, `status: CRITICAL` model-quality record; only provider/transport failures are retryable with `--retry-failures`.

## Tag decision

Phase 14 v3 deliberately removes tags from planner interpretation. Former generic tags such as idea, decision, reflection, review, explore, and someday are normally semantic concepts represented in note text and embeddings. If a concrete product workflow needs exact state (for example, “must review”), Core should later introduce an explicit schema property designed for that behavior. Existing Core tag storage remains temporarily for compatibility and is not exposed here; its removal is a separate migration decision after v3 validation.
