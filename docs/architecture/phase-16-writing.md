# Phase 16 writing checkpoint

Status: design checkpoint for Phase 16.2 / 16.3. Implementation is tracked in GitHub issue #36.

## Principle

Odyssey should not pay for a generative writer merely because knowledge is being created or updated.

The default write path is local and deterministic. Generative writing is a fallback for semantic reconciliation or an explicit type writing skill.

```text
KnowledgeUnit + WriteTargetDecision
                |
                v
       deterministic structure
      properties / controlled tags
                |
                v
            free-text fact
                |
        exact normalized check
          /              \
     duplicate            new/unknown
       |                     |
   NO_CHANGE                 v
                        MiniLM local gate
                         /            \
                  clearly new      overlap/unclear
                      |                 |
                    APPEND              v
                                  semantic writer
                                    Phase 16.3
```

MiniLM here is the existing local embedding model, not a generative LLM. Reuse `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` through the existing `TextEmbedder` boundary.

## Phase 16.2 — deterministic writing and novelty gate

Phase 16.2 owns the cheapest safe path.

It should:

- apply canonical property mutations deterministically;
- merge explicit controlled tag additions/removals deterministically;
- detect exact/normalized free-text duplicates locally;
- compare new facts with small existing body units using the existing MiniLM embedding runtime;
- allow deterministic APPEND only when benchmark evidence shows the fact is clearly independent;
- return a typed semantic-writer escalation when overlap is plausible or confidence is insufficient;
- reuse Phase 12 persistence for schema validation, revisions and lifecycle metadata;
- never let MiniLM authorize REPLACE or REMOVE.

The MiniLM threshold must be benchmarked rather than guessed. Optimize for high recall of semantic overlap: a false positive merely spends a later writer call, while a false negative can pollute the knowledge base.

Representative cases:

```text
Existing: Marta trabaja en Airbus.
New:      Marta trabaja en Airbus.
=> exact duplicate -> NO_CHANGE

Existing: Marta trabaja en Airbus.
New:      Marta es empleada de Airbus.
=> semantic overlap -> semantic writer

Existing: Marta vive en Toulouse.
New:      Marta ahora vive en Lyon.
=> possible correction/current-value change -> semantic writer

Existing: Marta vive en Toulouse.
New:      Marta ha empezado clases de piano.
=> deterministic APPEND only if benchmark evidence supports a safe threshold
```

Do not compare only against one whole-note embedding if that can hide individual facts. Start with the smallest useful deterministic body units (for example list items or paragraphs) and avoid a complex Markdown AST unless evidence requires it.

### CREATE

A CREATE decision does not imply a generative writer.

Without an explicit writing skill, a new note may be materialized deterministically when Odyssey can construct the complete note safely from validated planner output plus deterministic ID/name/path policy.

Never persist a partial note that silently drops free-text facts. Contextual unnamed entities such as `la amiga de Marta` remain valid logical entities; a proper name is not required for creation authorization.

## Phase 16.3 — semantic/specialized writer

Phase 16.3 is the expensive fallback, not the normal path.

Use it when:

1. existing free text must be semantically reconciled, amended or removed; or
2. the canonical note type has an explicit writing skill/profile that requires specialized organization or formatting.

The semantic writer should produce bounded operations rather than rewriting the entire note blindly. Candidate operations remain conceptually:

```text
NO_CHANGE
REPLACE exact old text -> new text
REMOVE exact old text
INSERT_AFTER exact anchor
APPEND
```

Core must validate exact anchors/current revision before persistence.

A writing skill controls presentation/organization, not whether a type may be created. There are no per-type creation permission rules.

## Cost model

The intended common path is:

```text
planner                    existing call
identity resolution        local when exact; existing contextual fallback only if needed
write novelty gate         existing local MiniLM
simple writer              deterministic
                           ----------------
additional generative writer calls: 0
```

Only ambiguous semantic edits or explicit writing skills add a writer-model call.

## Deferred Phase 16 work

Still outside this checkpoint:

- explicit bulk write cardinality;
- wikilink/reference dependency materialization;
- soft-delete persistence (`status: deleted` direction already chosen);
- RequestPlan action orchestration (Phase 17);
- n8n integration.

## Evidence gate

Before implementing automatic MiniLM-backed APPEND, benchmark duplicate/paraphrase/correction/independent pairs. If no robust low-risk separation exists, fail closed and send more cases to Phase 16.3 rather than lowering safety to save model calls.

### Phase 16.2A local MiniLM benchmark (2026-08-24)

The initial reproducible evidence is in
[`benchmarks/phase16_novelty_cases.json`](../../benchmarks/phase16_novelty_cases.json) and
[`benchmarks/phase16_novelty_results.json`](../../benchmarks/phase16_novelty_results.json). It is a
60-pair synthetic fact-unit benchmark (38 `OVERLAP`, 22 `INDEPENDENT`) executed with the existing
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` through
`FastEmbedTextEmbedder` / FastEmbed 0.7.3.

The existing local artifact is a complete Hugging Face Hub snapshot for FastEmbed's approved
`qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q` source. FastEmbed 0.7.3 otherwise attempts
an online metadata lookup even when that snapshot is complete. The embedder now exposes
`local_files_only=True` (the default), so normal use fails clearly rather than depending on a
network download. Run the evidence locally with a known model cache:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python benchmarks/run_phase16_novelty.py \
  --cache-dir /path/to/fastembed-cache
```

Similarity distributions were:

| Expected class | Min | Median | Max |
| --- | ---: | ---: | ---: |
| `OVERLAP` | 0.321 | 0.900 | 1.000 |
| `INDEPENDENT` | -0.038 | 0.299 | 0.853 |

At `T = 0.30` (`similarity < T` is the only local-append candidate), all 38 overlap pairs
escalated and 11/60 pairs (18.3%) could remain local. At `T = 0.40`, two overlap cases would append
unsafely: an employer temporal update and a related running fact. The Markdown probe measured 0.970
for a plain fact versus the same unordered-list item; paragraph/list equivalence ranged from 0.791 to
0.916. A later trivial line/list-item/paragraph projection is sufficient to investigate; a Markdown
AST is not justified by this evidence.

Exact duplicate normalization is intentionally narrower: trim surrounding whitespace, collapse
whitespace, and remove one conventional unordered-list marker. It preserves case, punctuation,
accents, negation, and word choice.

**Assessment: PROMISING, not a production threshold.** The zero-false-negative synthetic zone has
only a 0.021 gap below the lowest overlap case and must undergo larger, adversarial validation before
any automatic APPEND is enabled. No production write gate, APPEND, or semantic writer is implemented
by this checkpoint.
