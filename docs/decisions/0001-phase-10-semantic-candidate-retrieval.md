# ADR 0001: Phase 10 semantic candidate retrieval

- Status: Accepted retrospectively
- Decision date: 2026-08-17 (merged implementation)
- Recorded: 2026-08-17

## Context

Phase 9 resolves exact primary names and aliases but intentionally leaves relationship descriptions,
roles, and paraphrases unresolved. The next layer needed to retrieve a small set of plausible notes
without turning similarity into an identity decision. Markdown had to remain authoritative and the
target Raspberry Pi did not justify another service.

This record is retrospective. It records only rationale established by the merged Phase 10 code,
documentation, benchmark, and commit history; it does not infer undocumented historical motives.

## Decision

Use FastEmbed's multilingual MiniLM L12 v2 projection and exact cosine ranking to retrieve typed
Top-N candidates from a disposable SQLite index. Keep the API candidate-only: it exposes evidence
but applies no identity threshold, contextual outcome, LLM call, or vault write.

```text
authoritative Markdown --> validated projection --> disposable SQLite index
reference + context ------------------------------> typed Top-N evidence
                                                     (no identity decision)
```

The merged Phase 10 benchmark reported 16/16 Recall@5 for both tested multilingual embedding
models. MiniLM was selected because it matched that coverage with about 220 MB rather than about
1 GB and ran the measured embed/query workload in 0.49 s rather than 1.54 s. SQLite avoided a new
vector service while providing one atomic, inspectable, rebuildable file.

## Alternatives recorded in the merged decision

- Multilingual MPNet: equal measured Recall@5 with greater disk and runtime cost.
- Loose NumPy/files: little dependency reduction and weaker file coordination.
- `sqlite-vec`: native extension complexity before scale required accelerated search.
- Qdrant/Qdrant Edge: an operational boundary with no demonstrated V1 benefit.

## Consequences

Candidate retrieval is local and replaceable, but callers must rebuild the index explicitly after
source changes. Exact scanning is appropriate only while measured collection size and latency stay
small. Similarity scores cannot be interpreted as identity confidence. Phase 11 owns any later
contextual decision and must distinguish retrieval misses from decision failures.

The complete implemented contract remains in
[`semantic-retrieval.md`](../architecture/semantic-retrieval.md).

## Phase 11B.1c scale stress follow-up

A deterministic 1,000-note, 40-query adversarial stress test found 77.5% Recall@5 and Recall@10 for
the unchanged dense retriever, substantially below the original 16/16 small benchmark. On the
contextual-only slice, broad MiniLM recall was 72% at Top-5, 80% at Top-20, 88% at Top-50, and 100%
at Top-100. This fixture therefore points primarily to candidate reduction/ranking risk, while not
proving arbitrary future real-vault recall. One local hybrid experiment using name/alias overlap,
NLTK WordNet/OMW 1.4 synonym evidence, and reciprocal-rank fusion reached 80.0% Recall@5 and
Recall@10 but caused five new Top-5 misses, had important multilingual gaps, and added
disproportionate resource and deployment complexity. The tested mMARCO Cross-Encoder reranker did
not improve contextual Top-5 beyond 72% and added substantial ARM64 resource cost. Both approaches
are rejected/deferred; Phase 10 production behavior and dependencies are unchanged. Full evidence
is recorded in [`phase11b1c_retrieval_stress_results.md`](../../benchmarks/phase11b1c_retrieval_stress_results.md).

Retrieval must be re-evaluated against real Odyssey data as the vault grows. This synthetic
1,000-note stress test demonstrates a scale risk; it is not evidence that retrieval will remain
adequate at 10,000 or 100,000 real notes. Future safe candidate reduction and per-note retrieval
summaries are tracked in GitHub issue #20; they are intentionally deferred.
