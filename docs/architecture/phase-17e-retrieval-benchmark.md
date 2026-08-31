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
schema-v3-compatible scale corpus of 1,000 entities and 22 queries total. Scale single-target
oracles combine company, city, subject, and activity attributes; deterministic tests prove one
matching entity per query. Scale notes include 21-, 51-, and 101-fact controlled dilution tiers;
fact projections include approximately 65-, 85-, and 171-word coherent long-fact tiers.

| Strategy | Entity Recall@5/20/50/100 | Exact Fact Recall@5/20/50/100 | Units / vectors | Build s | Query s |
|---|---|---|---:|---:|---:|
| Whole-note | 72.7% / 77.3% / 90.9% / 90.9% | N/A | 1,000 / 1,000 | 96.10 | 0.97 |
| Fact-level | 68.2% / 86.4% / 86.4% / 86.4% | 63.6% / 68.2% / 68.2% / 68.2% | 5,142 / 5,142 | 104.09 | 3.47 |
| Combined | 77.3% / 86.4% / 90.9% / 90.9% | 68.2% / 68.2% / 72.7% / 77.3% | 5,142 / 6,142 | 199.72 | 8.41 |

Whole-note indexed 1,536,000 float32 vector bytes; fact-level indexed 7,898,112; combined
9,434,112. At Top 5, mean raw retrieved payload was approximately 1,353 tokens for whole-note,
174 for fact-level, and 155 for combined. At Top 100, means were approximately 14,255, 2,035,
and 2,049 tokens. These are characters/4 planning estimates, not provider-tokenizer counts.

The corrected aggregate does not support a production adoption decision: combined improves Top-5
entity recall but ties whole-note at Top-50/100 and has higher query/vector cost, while fact-level
has weaker Top-5 entity recall and lower exact-fact recall. Recommendation: **INSUFFICIENT EVIDENCE**.
The isolated controls found no rank degradation: the shared target ranked 1 at every 21/51/101-fact
note tier for all three strategies; the 65/85/171-word target fact ranked 1 at every fact-length
tier for fact-level and combined (whole-note exact-fact rank is not applicable). This is a null
result on the controlled fixture, not proof that dilution cannot occur. The recommendation remains
**INSUFFICIENT EVIDENCE** because aggregate strategy differences are modest, cost-sensitive, and
the planner precondition is blocked. This remains retrieval evidence only and does not authorize
writes or change production retrieval. The corpus is deterministic and synthetic; its scale queries
and distractors do not represent a live vault distribution.

## Historical MiniLM regression sentinel

The frozen Phase 11B.1c 1,000-note/40-query dense retrieval sentinel was rerun with the same
multilingual MiniLM artifact from `/data/odyssey/runtime/phase11a-benchmark/embedding-cache`.
The smallest schema-v3 compatibility adaptation was benchmark-only: the retired scalar
`relationship_to_user` metadata field was omitted while its wording remained in the frozen note
body, and the old scalar audit fields were represented using the current typed metadata shape.
Query and oracle semantics were not changed.

| Set | Recall@5 | Recall@20 | Recall@50 | Recall@100 | Historical @20/@50/@100 |
|---|---:|---:|---:|---:|---:|
| All 40 | 82.5% | 90.0% | 95.0% | 97.5% | 87.5% / 92.5% / 100% |
| Contextual-only 25 | 76.0% | 84.0% | 92.0% | 96.0% | 80% / 88% / 100% |

Top-100 does **not** remain 100%: one French synonym-mismatch query (`ma femme`) ranked its
historical expected entity at 105. This is a regression-sentinel failure relative to the frozen
baseline, although it is also a single known difficult synonym case. The Phase 17E recommendation
is therefore not reinterpreted; production retrieval remains unchanged and the evidence does not
support declaring a retrieval strategy adopted.

## Planner precondition

`run_planner_live.py` attempted 11 current production planner requests with `gpt-5.6-sol` and low
reasoning. All calls reached the planner boundary but failed with a sanitized `ConnectError` caused
by temporary DNS name-resolution failure; no Sol output was produced. Atomic-fact decomposition
remains unvalidated and is not used to justify the retrieval recommendation. A future rerun requires
provider access; no production prompt change is indicated by this blocked evidence.
