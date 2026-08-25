# Phase 16 writing checkpoint

Status: design checkpoint for Phase 16.2 / 16.3. Implementation is tracked in GitHub issue #36.

## Principle

Odyssey should not pay for a generative writer merely because knowledge is being created or updated.

The default structured write path is local and deterministic. Generative writing is a bounded fallback
for existing-note semantic reconciliation or an explicit type writing skill.

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
     duplicate       not exact duplicate
       |                     |
   NO_CHANGE                 v
                         bounded writer
                           Phase 16.3
```

MiniLM here is the existing local embedding model, not a generative LLM. Reuse `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` through the existing `TextEmbedder` boundary.

## Phase 16.2 — deterministic writing and novelty gate

Phase 16.2 owns the cheapest safe path.

It should:

- apply canonical property mutations deterministically;
- merge explicit controlled tag additions/removals deterministically;
- detect exact/normalized free-text duplicates locally;
- return a typed bounded-writer escalation for remaining free-text reconciliation;
- reuse Phase 12 persistence for schema validation, revisions and lifecycle metadata;
- never let MiniLM authorize REPLACE or REMOVE.

Exact normalized duplicates remain deterministic. Free-text non-duplicates do not receive an
autonomous local APPEND authorization from MiniLM or NLI evidence; the bounded writer benchmark
decides whether direct writer calls are cheap and reliable enough to avoid more local routing layers.

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

## Phase 16.3 — semantic/specialized writer benchmark

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

Core must validate exact anchors/current revision before persistence. Issue #38 freezes a synthetic,
cost-first benchmark: Luna runs all cases first, Terra receives only Luna material failures, and Sol
receives only remaining Terra material failures. It does not implement or productionize a writer.

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

### Phase 16.2A.2 adversarial Markdown-body benchmark (2026-08-24)

The separate 46-scenario synthetic adversarial dataset and measured output are
[`phase16_adversarial_novelty_cases.json`](../../benchmarks/phase16_adversarial_novelty_cases.json)
and
[`phase16_adversarial_novelty_results.json`](../../benchmarks/phase16_adversarial_novelty_results.json).
It reuses exactly the same offline MiniLM/FastEmbed 0.7.3 runtime as 16.2A. It compares planner-style
atomic facts with (A) the complete Markdown body, (B) the maximum score over simple body units
(unordered-list item, paragraph, or plain line), and (C) the maximum score over adjacent two-unit
blocks. It also includes raw-request probes; no planner was built or invoked.

| Strategy | `OVERLAP` min / median / max | `INDEPENDENT` min / median / max | Assessment |
| --- | ---: | ---: | --- |
| Whole note | 0.197 / 0.481 / 0.768 | 0.263 / 0.451 / 0.853 | UNSAFE |
| Unit-MAX | 0.178 / 0.562 / 1.000 | 0.151 / 0.603 / 0.853 | PROMISING, but unsafe for production |
| Block-MAX | 0.179 / 0.572 / 0.891 | 0.184 / 0.468 / 0.853 | UNSAFE |

Units demonstrate the buried-fact benefit: the buried exact Airbus fact was 0.341 whole-note versus
0.919 Unit-MAX, and its exact normalized unit match was found without MiniLM. They do not make a
safe gate: the buried Airbus → Thales update reached only 0.236 Unit-MAX, while the same-topic but
independent Toulouse-work case reached 0.853. At the first threshold that allows any known
independent local candidate, Unit-MAX `T=0.18` already has one dangerous false negative (the
gym-cessation update); whole-note `T=0.20` has one (two-to-three-children update); Block-MAX
`T=0.18` has one (French-language negation). `T=0.15` has zero false negatives for all three, but
also zero local candidates. Higher required thresholds only add false negatives.

Raw requests are noisier evidence than their expected atomic facts. For the multi-fact request,
raw-to-note was 0.539 while the atomic Lyon update was 0.602 whole-note / 0.768 Unit-MAX and the
independent piano fact was 0.404 / 0.366. The short-note raw independent violin request was 0.678,
versus 0.263 for its atomic fact. This supports planner atomization as the benchmark input.

Cross-language evidence is also conservative rather than decisive: the French buried Airbus →
Thales update was 0.385 whole-note / 0.373 Unit-MAX, while an independent Spanish guitar fact was
0.309 / 0.271. The benchmark therefore recommends **NONE_SAFE** for production integration now:
Unit-MAX is the most informative projection for a future, larger benchmark, but all strategies must
continue to fail closed. No production threshold is frozen, and no production APPEND or Phase 16.3
writer is implemented by this evidence checkpoint.

### Phase 16.2A.3 local multilingual NLI benchmark (2026-08-25)

[`phase16_nli_results.json`](../../benchmarks/phase16_nli_results.json) reuses all 46 adversarial
scenarios (25 `OVERLAP`, 21 `INDEPENDENT`) while keeping oracle-unit NLI separate from embedding
retrieval plus NLI. The experimental sequence classifier is
`MoritzLaurer/multilingual-MiniLMv2-L12-mnli-xnli` at revision
`0d55db361c5f291640208c51ff8c181146aa8eff` (Transformers 4.57.3, Torch 2.9.1+cpu, Safetensors
0.7.0). It is not a replacement for the existing retrieval embedding MiniLM.

Every pair preserves entailment/neutral/contradiction probabilities in both directions. A small
predeclared conservative grid (high neutral and low entailment/contradiction for every direction and
candidate) found no dangerous false-independent examples here, but escalated 11/21 independent facts
(52.4%) on oracle units, 14/21 at top-1 (66.7%), and 19/21 at top-3/top-5 (90.5%). This is not a
useful autonomous append zone. Retrieval recall for labelled overlap oracle units was 92% at top-1
(the English and French buried Airbus → Thales updates missed), then 100% at top-3/top-5.

Bidirectionality materially helped: Airbus → Thales had maximum contradiction 0.997 despite one
direction being 0.966 neutral; Toulouse → Lyon reached 0.997, gym cessation 0.991, and French
Airbus → Thales 0.947. Related independence can still be over-escalated: dog ownership → food
donation got reverse entailment 0.994, while Airbus → museum was clean (minimum neutral 0.949).
Raw bundled request evidence was contradiction-like where its planner-style atomic piano fact was
neutral (minimum neutral 0.992), reinforcing atomization; no planner was invoked.

The exact model/tokenizer were downloaded once outside the vault to `/home/ragdehl/.cache/odyssey-nli`
(about 470 MiB model snapshot; no binaries are committed). A rerun with `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` used local files only. On this Raspberry Pi CPU, load took 7.62 s and
one/three/five-pair batches took 72/88/94 ms; peak benchmark RSS was about 1.25 GiB.

**Assessment: NLI_PROMISING.** It materially improves semantic judgement over cosine similarity, but
the escalation rate and small synthetic corpus prevent productionization. Run larger held-out NLI
validation next; do not evaluate LLaMA or Qwen automatically. No production write gate, APPEND,
writer, or Phase 16.3 implementation exists.
