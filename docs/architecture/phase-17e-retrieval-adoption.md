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
authoritative Markdown re-grounding
        |
        v
bounded grounded evidence -> strong model
```

## Frozen fusion rule

Use the benchmarked deterministic reciprocal-rank fusion unchanged for notes that have atomic facts. For each whole-note rank and atomic-fact rank (both one-based), the score is:

```text
1 / (60 + whole_note_rank) + 1 / (60 + atomic_fact_rank)
```

The whole-note score is applied to each fact unit belonging to that note; ties use stable unit order. This is fixed evidence fusion, not a learned reranker, semantic threshold, second LLM, graph retrieval, or ranking service.

The benchmark's Combined ranking contains fact units, with whole-note rank acting as a global signal; it does not itself emit a whole-note result unit. Production must therefore preserve a deterministic compatibility fallback for an active note that has **no atomic-fact units**: keep one whole-note fallback candidate using the whole-note reciprocal-rank contribution `1 / (60 + whole_note_rank)`. This fallback prevents currently valid factless/metadata-only notes from disappearing. It does not change the benchmark recall claim and must be covered explicitly by the implementation tests.

## Production context boundary

Combined candidate ranking and final strong-model context are different boundaries.

For a normal atomic-fact hit, the final context must **not** hydrate the entire note body merely because that note was selected. Doing so would discard the principal precision/context-size benefit demonstrated by fact retrieval. Instead, the implementation must re-read the authoritative Markdown note, parse and validate it, verify note identity/source freshness, and re-ground the selected atomic fact by its existing Odyssey fact locator/text before exposing that exact current fact as evidence.

Whole-note rank for a note with atomic facts is ranking/global-entity evidence only and does not independently inject the whole note into final context. Multiple selected facts from the same note are deduplicated by fact identity and may be grouped under one note identity for presentation, while preserving the number and order of grounded evidence units.

For the explicit factless-note fallback, the current authoritative note body/projection may be returned as one bounded whole-note evidence unit because no atomic fact exists to hydrate. This is a compatibility path, not the default for factful notes.

The current `ContextPackage` stores full `note.content`, so the subsequent implementation may need the **smallest compatible extension** of the context result shape to carry grounded fact evidence. Reuse the existing vault read, parse, schema validation, source-hash, deletion, and identity guards; do not pretend the current full-note `ContextItem.content` contract already provides compact fact context.

Missing, deleted, malformed, identity-mismatched, removed-fact, or stale indexed material must fail closed or be skipped only where the existing context contract already permits that behavior. Semantic ranking remains evidence only and never authorizes identity resolution, writes, bulk mutation, or schema changes.

Top-500 is the independent raw local candidate limit. The caller-visible final context budget remains independently bounded: after authoritative grounding and deduplication, retain at most the caller-requested final `limit` **grounded evidence units** in fused rank order, then group them by note only for representation. Grouping must not silently add extra facts or full note bodies. No numeric strong-model token budget is invented here; measurement-only tuning belongs to Phase 19/E2E work.

## Final contract

- **Retrieval strategy:** Combined whole-note + atomic-fact retrieval.
- **Candidate width:** Top-500 raw local Combined candidates.
- **Fusion rule:** Exact tested fixed reciprocal-rank fusion with `RRF_K = 60`, summing one-based whole-note and fact reciprocal-rank contributions for fact units.
- **Factless compatibility:** One whole-note fallback candidate for an active note with no atomic facts, scored from the whole-note reciprocal-rank contribution only; no benchmark-recall claim is attached to this fallback.
- **Authoritative grounding:** Current authoritative Markdown vault; re-read and validate the note, then expose the exact currently grounded selected fact rather than the whole body for normal fact hits.
- **Final-context policy:** After grounding/deduplication, at most the caller-requested final `limit` evidence units are retained in fused rank order; grouping by note is representational and must not expand the evidence set.
- **Whole-note payload:** Whole-note rank is ranking evidence only for factful notes; full-note content is allowed only for the explicit factless fallback.
- **Insufficient-evidence behavior:** Return bounded incomplete evidence or fail closed; never infer missing knowledge from ranking scores.
- **Authority:** Retrieval is evidence only and has no write, identity, bulk-mutation, or schema authority.
- **Lean optimization candidate:** Top-300, to be reconsidered only with real E2E cost/recall evidence.
- **Implementation next step:** A separate production Combined retrieval implementation PR, including the minimal context-result representation change needed for grounded facts and deterministic tests for factless-note fallback.

## Open decisions

None for this adoption decision. Production implementation and later E2E budget tuning are subsequent scoped work, not unresolved adoption choices. Phase 17E as a whole remains incomplete until that implementation is completed; Phase 18 remains after the production retrieval checkpoint.
