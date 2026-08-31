# Phase 17E retrieval benchmark

Status: **benchmark evidence complete; planner decomposition evidence blocked by provider access**

This checkpoint compares the current whole-note retrieval projection with identity-preserving
atomic-fact units and a deterministic entity-plus-fact fusion. It is evidence only. Production
`ContextIndex`, Top-K, retrieval behavior, write authority, and schema are unchanged.

```text
canonical notes -> exact whole projection -> whole-note rank
               `-> identity + fact units -> fact rank
                                      `-> fixed reciprocal-rank fusion
```

The reproducible harness and frozen corpus are in
[`benchmarks/phase17e_retrieval/`](../../benchmarks/phase17e_retrieval/). Its 8-note/12-query
corpus covers long heterogeneous notes, short controls, Spanish, French, contextual identity,
entity disambiguation, exact atomic facts, and reusable historical identity patterns. The whole
projection calls the current `build_context_retrieval_text` directly. Fact projection is exactly:
`Name`, canonical `Type`, and `Fact`, with the marker-derived fact text preserved separately.

## Results

The diagnostic corpus (8 notes/12 queries) was retained and supplemented by a deterministic,
schema-v3-compatible scale corpus of 1,000 entities and 22 queries total. Scale notes include
21-, 51-, and 101-fact controlled dilution tiers; fact projections include approximately 65-,
85-, and 150-word coherent long-fact tiers.

| Strategy | Entity Recall@5/20/50/100 | Exact Fact Recall@5/20/50/100 | Units / vectors | Build s | Query s |
|---|---|---|---:|---:|---:|
| Whole-note | 68.2% / 72.7% / 72.7% / 81.8% | N/A | 1,000 / 1,000 | 94.79 | 0.85 |
| Fact-level | 72.7% / 72.7% / 77.3% / 77.3% | 68.2% / 72.7% / 77.3% / 77.3% | 5,142 / 5,142 | 103.03 | 3.60 |
| Combined | 72.7% / 72.7% / 77.3% / 77.3% | 72.7% / 72.7% / 77.3% / 77.3% | 5,142 / 6,142 | 199.72 | 8.57 |

Whole-note indexed 1,536,000 float32 vector bytes; fact-level indexed 7,898,112; combined
9,434,112. At Top 5, mean raw retrieved payload was approximately 1,353 tokens for whole-note,
173 for fact-level, and 155 for combined. At Top 100, means were approximately 14,262, 2,034,
and 2,045 tokens. These are characters/4 planning estimates, not provider-tokenizer counts.

The result supports **ADOPT COMBINED**: it improves exact-fact recall over fact-only and entity
recall over whole-note on this corpus, while materially increasing build/vector/query cost. This
remains retrieval evidence only and does not authorize writes or change production retrieval.
The corpus is deterministic and synthetic; its scale queries and distractors do not represent a
live vault distribution.

## Planner precondition

`run_planner_live.py` attempted 11 current production planner requests with `gpt-5.6-sol` and low
reasoning. All calls reached the planner boundary but failed with the same provider-call error;
no Sol output was produced. Atomic-fact decomposition remains unvalidated and is not used to
justify the retrieval recommendation. A future rerun requires provider access; no production
prompt change is indicated by this blocked evidence.
