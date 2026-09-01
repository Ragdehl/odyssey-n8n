# Phase 17E retrieval adoption decision

Status: **completed focused subphase; production implementation remains next**

## Decision

Adopt **Combined whole-note + atomic-fact retrieval** for the subsequent production implementation PR. The initial local candidate width is **Top-500**. This is an architecture decision only: production `ContextIndex`, `get_context`, and retrieval behavior remain whole-note only until that implementation is separately reviewed and merged.

Top-400 was intentionally not rerun. Complete ranked Combined outputs were not preserved, and the known `scale-100` last required fact is rank 412, so Top-400 cannot reach the decisive 100% result. The exact aggregate would not materially distinguish the adoption trade-off; regenerating it was disproportionately expensive for this synthetic fixture.

## Preserved evidence and width comparison

| Combined width | Entity recall | ALL required-fact recall | Raw candidate payload |
|---:|---:|---:|---:|
| 200 | 90.9% | 95.5% | ~4,054 tokens |
| 300 | 95.5% | 95.5% | ~5,959 tokens |
| 400 | Not measured | At most 95.5% | Not measured |
| 500 | 100% | 100% | ~9,729 tokens |

ANY required-fact recall was 100% at measured 200, 300, and 500 widths; mean/median coverage was 98.5% / 100% at 200 and 300, and 100% / 100% at 500. Top-400 is not estimated. Its known rank-412 miss proves only that its ALL-required-fact recall is below 100% on this fixture.

The marginal gains are uneven. 200 → 300 adds 4.6 percentage points of entity recall but no ALL-fact improvement. 300 → 400 has an unmeasured aggregate and cannot recover `scale-100`'s last fact. 400 → 500 is the only measured step that reaches full entity and ALL-fact recall, at a substantial payload increase. Top-500 is therefore the initial breadth choice, not a universal recall guarantee. Top-300 is the lean fallback if real E2E measurements show that its lower breadth is sufficient; Top-200 remains an efficient evidenced alternative.

These are local candidate costs, not strong-model context costs:

```text
Combined Top-500 local candidates
        |
        v
current authoritative Markdown hydration and validation
        |
        v
deduplicated bounded context package -> strong model
```

## Frozen fusion rule

Use the benchmarked deterministic reciprocal-rank fusion unchanged. For each whole-note rank and atomic-fact rank (both one-based), the score is:

```text
1 / (60 + whole_note_rank) + 1 / (60 + atomic_fact_rank)
```

The whole-note score is applied to each fact unit belonging to that note; ties use stable unit order. This is fixed evidence fusion, not a learned reranker, semantic threshold, second LLM, graph retrieval, or ranking service.

## Production context boundary

The subsequent implementation should reuse `ContextIndex.find_candidates` and `get_context`. Combined whole-note and fact hits are associated by authoritative note ID/path. Whole-note hits supply global entity/ranking signal; fact hits supply precise evidence. They do not become separate final context entries. The note is selected once, then its current Markdown body is read, parsed, schema-validated, identity-checked, and returned through the existing `ContextPackage`. This hydrates fact evidence from the source of truth and prevents duplicate whole/fact payload for one note.

Missing, deleted, malformed, identity-mismatched, or stale indexed material must fail closed using existing context retrieval errors/guards. Semantic ranking remains evidence only and never authorizes identity resolution, writes, bulk mutation, or schema changes.

Top-500 is an independent local candidate limit. Final context must use the existing bounded `get_context(..., limit=...)` / `ContextPackage` boundary, with a deterministic bounded note/context policy from hydrated candidates rather than forwarding all 500 units. No numeric strong-model token budget is invented here; measurement-only tuning belongs to Phase 19/E2E work.

## Final contract

- **Retrieval strategy:** Combined whole-note + atomic-fact retrieval.
- **Candidate width:** Top-500 local Combined candidates.
- **Fusion rule:** Exact tested fixed reciprocal-rank fusion with `RRF_K = 60`, summing one-based whole-note and fact reciprocal-rank contributions.
- **Authoritative grounding:** Current authoritative Markdown vault; group by note identity and hydrate/validate each selected note once through the existing Core context boundary.
- **Final-context policy:** Bounded independently from candidate width using the existing bounded `get_context`/`ContextPackage` contract; do not send all raw candidates to the strong model.
- **Insufficient-evidence behavior:** Return bounded incomplete evidence or fail closed; never infer missing knowledge from ranking scores.
- **Authority:** Retrieval is evidence only and has no write, identity, bulk-mutation, or schema authority.
- **Lean optimization candidate:** Top-300, to be reconsidered only with real E2E cost/recall evidence.
- **Implementation next step:** A separate production Combined retrieval implementation PR.

## Open decisions

None for this adoption decision. Production implementation and later E2E budget tuning are subsequent scoped work, not unresolved adoption choices. Phase 17E as a whole remains incomplete until that implementation is completed; Phase 18 remains after the production retrieval checkpoint.
