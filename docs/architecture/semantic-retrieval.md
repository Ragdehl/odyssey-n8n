# Semantic Candidate Retrieval

## Phase 10 boundary

Phase 10 retrieves a small ranked set of plausible existing notes when exact Phase 9 evidence is
insufficient. It does not decide identity:

```text
reference + surrounding context
              |
              v
find_semantic_entity_candidates
              |
              v
ranked candidate evidence          contextual resolution [PHASE 11]
  id / path / type / name / score  ----------------------> NOT IMPLEMENTED
```

Cosine similarity is ranking evidence, not identity confidence. The candidate type intentionally
contains no resolution outcome. Phase 10 calls no LLM, applies no identity threshold, writes no
canonical note, and does not implement `resolve_entity`.

## Retrieval projection

`build_semantic_retrieval_text(note, path)` deterministically produces one embedding input per
validated atomic note. It includes the filename-derived primary name, aliases, canonical type,
non-technical domain metadata, and Markdown body. Ordinary wikilinks contribute their visible
label, or their target when no label exists:

```text
people/Beatriz Costa.md + Partner of [[people/Xavi|Xavi]].
    -> Name: Beatriz Costa
       Type: person
       Partner of Xavi.
```

Technical lifecycle metadata such as timestamps, actors, revision, and schema version is omitted
because it adds no useful semantic identity evidence. There is no chunking or graph traversal.

## Derived index

`SemanticEntityIndex.rebuild(repository, schema, embedder)` lists, reads, parses, and validates the
entire Markdown vault before atomically replacing one SQLite file. It records stable ID, path,
canonical type, primary name, SHA-256 source hash, model/runtime identity, and one normalized
float32 embedding per note. Explicit Odyssey application, index-format, and format-version markers
identify the disposable file. Duplicate IDs and invalid notes fail closed; a failed rebuild
preserves the previous index. `delete()` refuses to unlink a file unless those markers verify it as
an Odyssey semantic index.

The caller must place the index outside canonical vault knowledge, for example:

```text
/data/odyssey/vault/                    authoritative Markdown
/data/odyssey/runtime/semantic.sqlite3  disposable derived index
```

There is no watcher, daemon, incremental synchronization, additional service, or new source of
truth. A caller rebuilds explicitly after source changes. The index opens read-only during query.

## Public API

```python
find_semantic_entity_candidates(
    index,
    embedder,
    "the other Beatriz",
    context="Dinner with Xavi and the other Beatriz",
    type="person",
    limit=5,
)
```

The optional type filter is checked against canonical types recorded at rebuild and applied before
top-N selection. Ranking is exact cosine comparison over all filtered note embeddings. Equal scores
use primary name, path, then stable ID for deterministic ordering. The index model and query model
must match.

## Model and backend decision

The synthetic dataset in `benchmarks/phase10_semantic_cases.json` contains people, stores, a project,
and a concept, with English, Spanish, French, and Catalan references. Both benchmarked FastEmbed
models put the expected entity in Top 5 for all 16 cases on ARM64:

| Model | Recall@5 | Model size | Embed + query time |
| --- | ---: | ---: | ---: |
| multilingual MiniLM L12 v2 | 16/16 | about 220 MB | 0.49 s |
| multilingual MPNet base v2 | 16/16 | about 1 GB | 1.54 s |

The selected V1 model is
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` through FastEmbed 0.7.3. The smaller
model had identical benchmark coverage and materially lower footprint and runtime. Model artifacts
are derived and downloaded locally; note text is not sent to an external embedding API.

SQLite is selected over a loose files/NumPy bundle because it provides one atomic, inspectable file
and needs no extra storage dependency. Exact cosine remains simple at hundreds to low thousands of
notes. A NumPy file bundle would reduce little complexity because FastEmbed already supplies NumPy,
while adding file-coordination concerns. `sqlite-vec` adds a native extension before scale requires
accelerated vector search. Qdrant/Qdrant Edge adds a vector engine and operational boundary with no
demonstrated V1 benefit. Reconsider only if measured rebuild/query latency or collection size makes
the exact scan inadequate.

Install the optional semantic runtime and run the repeatable non-CI checks with:

```bash
python -m pip install -r requirements-semantic.txt
python benchmarks/run_phase10_semantic.py
python -m scripts.smoke_semantic_retrieval
```

The quality benchmark is deliberately separate from deterministic CI. Focused CI tests use a fake
embedder to verify projection, rebuild/deletion, read-only source behavior, type filtering, top-N,
tie ordering, invalid-source handling, and the candidate-only contract without network or model
downloads.

## Deferred linked-note retrieval

A later context capability may add an API conceptually equivalent to
`get_linked_notes(note_id, depth=1)`. It can derive a small note neighborhood from ordinary
wikilinks when a concrete `get_context` requirement exists. Phase 10 adds no graph traversal,
backlink index, graph database, or linked-note API.

## Phase 13 general knowledge context retrieval

Phase 13 implements `get_context` for a different responsibility: retrieving notes that contain
knowledge relevant to an already-interpreted query. It does not resolve identity, interpret
natural-language requests, or generate answers:

```text
interpreted query -> get_context -> ContextIndex -> ranked atomic notes
                                      |
                                      +--> authoritative Markdown content
```

`ContextIndex` is a separate disposable SQLite derived index. It stores one normalized local
embedding per whole atomic note, its source hash, canonical type, and controlled tags. The
projection includes filename name, aliases, type, subtype/domain metadata, tags, Markdown body,
and human-readable wikilinks; lifecycle and internal technical metadata are excluded. Tags are
context evidence and exact filters here, while remaining excluded from Phase 10 identity
projection and Phase 11 provider evidence.

The V1 API requires a non-empty query and explicit positive `limit`, with optional exact canonical
`type` and all-of `required_tags` filters applied before deterministic cosine top-N ranking.
Similarity is ranking evidence only. Selected candidates are reread and schema-validated from
the Markdown vault before becoming immutable `ContextItem` values; the vault remains the source
of truth. A changed selected source hash, invalid note, or indexed identity mismatch fails
explicitly. Rebuild is explicit and atomic, and a failed rebuild preserves the previous index.
V1 has no LLM, answer generation, graph traversal, chunking, reranking, or automatic refresh
orchestration. The index is also compatible only with the canonical type and tag registries stored
when it was built; registry drift fails explicitly and requires an explicit rebuild. Future
interpretation supplies the retrieval need.
