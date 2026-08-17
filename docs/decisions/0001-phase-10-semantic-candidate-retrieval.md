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
