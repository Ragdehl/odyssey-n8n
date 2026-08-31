# Phase 17E retrieval benchmark

Status: **benchmark implementation; real MiniLM evidence pending local model availability**

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

## Evidence status

The configured FastEmbed runtime is installed, but the offline MiniLM artifact was not present in
the local cache on 2026-08-31. The real runner therefore failed closed and no substitute model was
used. Deterministic fake-embedder tests pass and validate corpus/oracle/evaluation behavior, but
they cannot establish semantic retrieval quality, latency, or resource cost.

The final results table and recommendation must be added from a successful real run; until then the
correct recommendation is **INSUFFICIENT EVIDENCE**. Do not interpret deterministic test metrics as
MiniLM results. The missing evidence includes real Top 5/20/50/100 recall, long-vs-short behavior,
retrieved units versus unique entities, approximate downstream payload, build/query latency, and
local index/resource cost.
