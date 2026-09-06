# Semantic Retrieval

This document describes Odyssey's **current local retrieval responsibilities**. Historical model comparisons and phase-specific adoption evidence remain in ADRs and benchmarks.

## Two different retrieval jobs

Odyssey deliberately separates identity candidate retrieval from general knowledge retrieval.

```text
identity/reference resolution              knowledge retrieval
-----------------------------              -------------------
reference/context                           interpreted query
      |                                           |
      v                                           v
SemanticEntityIndex                         ContextIndex
      |                                           |
ranked possible identities                  ranked relevant notes/evidence
      |                                           |
contextual resolver if needed               consumer/answerer/planner use
```

Similarity is evidence in both cases. It is never mutation authority and is not by itself identity confidence.

## Local embedding model and storage

The established local embedding family is multilingual MiniLM (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) through the project's FastEmbed boundary. It was selected from bounded ARM64 evidence because it provided the required multilingual broad recall with materially lower footprint than the larger tested alternative.

Both semantic indexes are rebuildable SQLite artifacts outside the canonical vault. They are derived from validated current Markdown and can be replaced atomically after a successful rebuild.

```text
/data/odyssey/vault/                    authoritative Markdown
/data/odyssey/runtime/*.sqlite3         disposable derived indexes
```

A failed rebuild must not corrupt the previous usable index. Query-time selection is re-grounded against authoritative current Markdown where the active contract requires it.

Odyssey does not currently require a vector service, graph database, daemon, watcher, or approximate-nearest-neighbor infrastructure. Reconsider only from measured scale/latency evidence.

## Identity candidate retrieval

`SemanticEntityIndex` provides broad plausible candidates when exact canonical name/alias evidence is insufficient.

The projection contains identity-useful current note evidence while excluding technical lifecycle metadata that does not help semantic identity. Candidate results preserve stable ID/path/type/name and rank evidence for Core; the contextual resolver may choose only from the supplied candidate set, and Core validates its output.

Current composed identity behavior is documented in [Architecture Overview](overview.md) and historical Phase 9–11 ADRs. The important invariant is:

```text
semantic score -> candidate ranking evidence
semantic score != RESOLVED / AMBIGUOUS / UNRESOLVED authority
```

Broad candidate count remains an explicit caller choice where relevant. Earlier large-vault evidence showed that aggressive small Top-K can lose the correct candidate; later refinements must preserve recall before reducing context.

## General knowledge retrieval

`get_context` / `ContextIndex` retrieve knowledge relevant to an already-interpreted request. They do not interpret raw natural language, resolve identity, generate an answer, or authorize writes.

The current index stores a whole-note semantic projection plus filterable schema values needed for deterministic pre-filtering. Selected notes are reread/revalidated against current Markdown before becoming grounded context evidence under the active contract.

### Structured filters

Structured filters are accepted only for fields that the **current canonical schema** marks filterable. Operators/value validation are schema/type aware and compile to fixed parameterized SQLite predicates before semantic ranking.

Important current examples:

- `type` — exact controlled canonical type restriction;
- `created_at` / `updated_at` — lifecycle date-time ranges;
- `aliases` — exact array membership only when explicitly requested by the planner contract;
- `tags` — exact `contains` over **free-form explicit user/app values**;
- type-specific properties such as `journal_entry.entry_date` when registered/filterable.

The active schema has no general `subtype` field and no Core-owned controlled tag registry. Historical Phase 13–16 documents may describe older schema capabilities; [`config/note-schema.json`](../../config/note-schema.json) is the exact current authority.

Unknown fields, non-filterable fields, unsupported operators, invalid types/values, and invented controlled type IDs fail explicitly. Model-generated SQL is never executed.

## Relationship questions

Ordinary relationships are usually stored once as Markdown/wikilinks. The semantic projection humanizes `[[wikilinks]]`, so an inverse natural-language question can often retrieve the note that contains the relationship without writing an inverse fact into the other note.

```text
Laura: "responsable de [[Marta]]"
        |
        v
semantic query "¿Quién es responsable de Marta?"
        |
        v
Laura can be retrieved directly
```

Do not automatically duplicate inverse relations or run graph traversal for every relationship question.

Explicit structural questions such as “which notes link to Marta?” or bounded neighborhood/multi-hop requests may use graph/link-aware execution through the planner's explicit graph semantics. Graph retrieval is a separate capability, not the default semantic search path.

## Whole-note retrieval is still production baseline

Atomic facts now exist inside entity notes, but production retrieval has not adopted fact-level indexing/ranking as the default. Physical source of truth and retrieval unit are intentionally separable.

The next preserved evidence-driven work is [Future Retrieval Refinements](future-query-decomposed-retrieval.md):

1. test query decomposition and aggregation by canonical entity for real multi-clue misses;
2. only if candidate volume/cost becomes material, test a high-recall inexpensive selector;
3. only if full bodies are wasteful, test revision-bound compact retrieval evidence/fact projections.

No successful retrieval experiment gains write authority.

## Repeatable evidence

Deterministic CI uses fake/test embedders for index/projection/filter/validation behavior and does not download models. Quality/model comparisons remain explicit benchmark runs under `benchmarks/` and are not part of ordinary credential-free CI.

Install/run semantic dependencies only when the relevant local benchmark/smoke evidence is needed; current exact commands and pinned packages live with the benchmark/scripts rather than being duplicated as a permanent setup tutorial here.
