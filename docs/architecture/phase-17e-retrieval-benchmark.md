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

| Strategy | Entity Recall@5/20/50/100 | All-required-fact Recall@5/20/50/100 | Units / vectors | Build s | Query s |
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
has weaker Top-5 entity recall and lower all-required-fact recall. Recommendation: **INSUFFICIENT EVIDENCE**.
The isolated controls found no rank degradation: the shared target ranked 1 at every 21/51/101-fact
note tier for all three strategies; the 65/85/171-word target fact ranked 1 at every fact-length
tier for fact-level and combined (whole-note exact-fact rank is not applicable). This is a null
result on the controlled fixture, not proof that dilution cannot occur. The recommendation remains
**INSUFFICIENT EVIDENCE** because aggregate strategy differences are modest, cost-sensitive, and
the planner precondition is blocked. This remains retrieval evidence only and does not authorize
writes or change production retrieval. The corpus is deterministic and synthetic; its scale queries
and distractors do not represent a live vault distribution.

## Fact-level width sweep

The fact-level arm was rerun once against the same 1,000-entity corpus and local MiniLM artifact;
the complete ranked fact list was then evaluated at each width. The machine-readable output keeps
per-query first-entity-fact and exact-fact ranks, plus misses at every width.

| Raw fact width | Raw-unit entity recall | All-required-fact recall | True unique-entity recall | Mean / median unique entities in raw cutoff |
|---:|---:|---:|---:|---:|
| 100 | 86.4% | 68.2% | 86.4% | 79.95 / 91 |
| 200 | 95.5% | 68.2% | 95.5% | 167.27 / 188.5 |
| 300 | 95.5% | 68.2% | 95.5% | 259.23 / 287 |
| 500 | 100.0% | 68.2% | 100.0% | 443.73 / 487 |

At raw widths 100/200/300/500, the maximum facts consumed by one entity had mean/median/max
values of 14.27/4/81, 18.23/4.5/101, 19.09/4.5/101, and 21.09/5/101 respectively. This shows
substantial repeated-unit occupancy in some rankings, while the raw and true unique-entity recall
values happen to coincide for these cases.

The fact-level misses are `scale-100`, `scale-400`, and `scale-700` at Top-100; only `scale-100`
remains at Top-200 and Top-300; none remain at Top-500. First expected-entity-fact ranks range
from 1 to 477 (median 2); required-fact ranks range from 1 to 208 (median 2). The complete per-query
rank list is retained in the benchmark JSON output rather than duplicated here.

| Raw fact width | Retrieved payload mean chars / approximate tokens | Grouped 1 / 2 / 3 facts per entity, mean approximate tokens |
|---:|---:|---:|
| 100 | 8,141 / 2,035 | 1,925 / 1,997 / 2,035 |
| 200 | 15,857 / 3,964 | 3,770 / 3,913 / 3,953 |
| 300 | 23,356 / 5,839 | 5,611 / 5,864 / 5,908 |
| 500 | 38,211 / 9,553 | 9,299 / 10,010 / 10,085 |

Grouped estimates retain the first ranked facts for the first K distinct entities and count each
identity-preserving `Name`/`Type`/`Fact` projection once per retained unit; they are planning
estimates, not a production grouping algorithm. For comparison, whole-note Top-100 payload has a
mean of approximately 57,019 chars / 14,255 tokens. Widening fact retrieval reaches full entity
recall only at 500 on this fixture, where its ungrouped payload is still smaller than whole-note
Top-100 but materially larger than fact Top-100. The improvement stops between 200 and 300, then
the final difficult case arrives only at 500, so fact-level remains a credible candidate but not
an adoption decision or a reason to add a production grouping algorithm. Recommendation remains
**INSUFFICIENT EVIDENCE**.

### Corrected multi-fact evidence

The earlier all-required-fact value is explicitly named here. `ANY` means at least one required
fact was retrieved; `ALL` means every required fact was retrieved; coverage is the fraction of
required facts present, averaged and median across the 22 cases with fact oracles. Whole-note
fact evidence is not applicable because whole-note units are not individual fact units.

| Strategy / width | Entity recall | ANY required fact | ALL required facts | Mean / median coverage |
|---|---:|---:|---:|---:|
| Whole-note / 100 | 90.9% | N/A | N/A | N/A |
| Fact-level / 100 | 86.4% | 95.5% | 68.2% | 78.8% / 100% |
| Fact-level / 200 | 95.5% | 95.5% | 68.2% | 78.8% / 100% |
| Fact-level / 300 | 95.5% | 100% | 68.2% | 80.3% / 100% |
| Fact-level / 500 | 100% | 100% | 68.2% | 80.3% / 100% |
| Combined / 100 | 90.9% | 100% | 77.3% | 89.4% / 100% |
| Combined / 200 | 90.9% | 100% | 95.5% | 98.5% / 100% |
| Combined / 300 | 95.5% | 100% | 95.5% | 98.5% / 100% |
| Combined / 500 | 100% | 100% | 100% | 100% / 100% |

The seven scale-contextual multi-fact cases are:

| Case | Expected entity | Facts | Coverage 100 / 200 / 300 / 500 | First / last required rank |
|---|---|---:|---:|---:|
| scale-100 | Scale Person 0100 | 3 | Fact 0/0/33/33%; Combined 33/67/67/100% | Fact 208 / 2089; Combined 47 / 412 |
| scale-250 | Scale Person 0250 | 3 | Fact 33/33/33/33%; Combined 67/100/100/100% | Fact 6 / 1948; Combined 3 / 136 |
| scale-400 | Scale Person 0400 | 3 | Fact 33/33/33/33%; Combined 100/100/100/100% | Fact 40 / 1653; Combined 36 / 73 |
| scale-550 | Scale Person 0550 | 3 | Fact 67/67/67/67%; Combined 67/100/100/100% | Fact 6 / 1563; Combined 8 / 138 |
| scale-700 | Scale Person 0700 | 3 | Fact 33/33/33/33%; Combined 67/100/100/100% | Fact 4 / 2028; Combined 8 / 123 |
| scale-850 | Scale Person 0850 | 3 | Fact 33/33/33/33%; Combined 33/100/100/100% | Fact 12 / 1823; Combined 11 / 133 |
| scale-999 | Scale Person 0999 | 3 | Fact 33/33/33/33%; Combined 100/100/100/100% | Fact 9 / 1298; Combined 2 / 44 |

Required fact ranks are preserved individually in each strategy's `fact_width.ranks` output;
`last` is null when the complete ranking does not contain every required fact. Fact-only does not
retrieve all three required facts for any of these seven within Top-500, whereas Combined reaches
all three for all seven by Top-500. Combined therefore reaches full entity and evidence recall at
the same width as fact-only, but reaches materially higher evidence completeness by Top-200. Its
Top-200 payload is approximately 4,054 tokens versus fact-only 3,964 and whole-note Top-100
14,255, so the safety-net gain has a measurable fusion cost. No production grouping, hydration, or
retrieval change follows from this benchmark.

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

### Retired relationship wording A/B

To test that explanation directly, the same frozen corpus, queries, MiniLM artifact, and query
construction were rerun with a benchmark-only projection variant. It appended
`Relationship To User: épouse` from the frozen `NoteSpec` to the affected note; it did not restore
the field to the schema or production notes, and did not change the query or oracle.

| Projection | `fr-wife-femme` rank | Recall@20 | Recall@50 | Recall@100 |
|---|---:|---:|---:|---:|
| Current schema-v3-compatible | 105 | 90.0% | 95.0% | 97.5% |
| Historical-equivalent wording | 18 | 95.0% | 100.0% | 100.0% |

The retired relationship wording restores the affected case and the sentinel Top-100 result, so
the one changed Top-100 outcome is explained on this fixture. There is no demonstrated broad
MiniLM degradation: current Recall@20 and Recall@50 are higher than the historical baseline, and
the difference is attributable to removal of an intentional schema-v2 semantic signal. This does
not justify restoring `relationship_to_user` to Odyssey Core. If a real need emerges, future
domain/application schema contributions can provide useful semantic signals through the approved
schema-ownership direction. The retrieval strategy recommendation remains **INSUFFICIENT
EVIDENCE**.

## Planner precondition

`run_planner_live.py` attempted 11 current production planner requests with `gpt-5.6-sol` and low
reasoning. All calls reached the planner boundary but failed with a sanitized `ConnectError` caused
by temporary DNS name-resolution failure; no Sol output was produced. Atomic-fact decomposition
remains unvalidated and is not used to justify the retrieval recommendation. A future rerun requires
provider access; no production prompt change is indicated by this blocked evidence.

A bounded environment diagnosis on 2026-09-01 found the required `OPENAI_API_KEY` variable present
without inspecting its value, but DNS resolution failed for both `api.openai.com` and
`api.github.com` with `gaierror: [Errno -3] Temporary failure in name resolution`. The current
blocker is therefore DNS resolution unavailable; authentication, model access, and planner
behavior could not be tested. No networking, credentials, or machine configuration was changed.
