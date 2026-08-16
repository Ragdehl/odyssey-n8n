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
float32 embedding per note. Duplicate IDs and invalid notes fail closed; a failed rebuild preserves
the previous index. `delete()` removes only the explicitly configured derived file.

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
and a concept, with English, Spanish, and French references. Both benchmarked FastEmbed models put
the expected entity in Top 5 for all 13 cases on ARM64:

| Model | Recall@5 | Model size | Embed + query time |
| --- | ---: | ---: | ---: |
| multilingual MiniLM L12 v2 | 13/13 | about 220 MB | 0.42 s |
| multilingual MPNet base v2 | 13/13 | about 1 GB | 1.58 s |

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
