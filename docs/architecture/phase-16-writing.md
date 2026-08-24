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
