# Phase 16 writing checkpoint

Status: Phase 16.3 benchmark complete; the writer policy is selected for the upcoming Phase 16
materialization work. Implementation remains tracked in GitHub issue #36.

## Principle

Keep the write path simple and fail closed.

Canonical structure remains deterministic. For free-text knowledge that is not an exact normalized
duplicate, Odyssey uses one bounded semantic writer policy rather than a ladder of local semantic
gates or model-routing conditions.

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
                  full authoritative note
                            |
                            v
                     Luna / medium
                            |
                            v
                    bounded operation
                            |
                            v
        Core exact-span / revision / schema validation
                            |
                            v
                      persistence
```

MiniLM and the experimental NLI model are **not** selected for within-note writer filtering or
semantic APPEND authorization. MiniLM remains useful elsewhere for broad retrieval where separate
recall evidence supports it.

## Phase 16.2 — deterministic structure and exact-duplicate shortcut

Phase 16.2 owns only work that is safely deterministic.

It should:

- apply canonical property mutations deterministically;
- merge explicit controlled tag additions/removals deterministically;
- detect exact/normalized free-text duplicates locally;
- hand remaining free-text reconciliation to the bounded writer;
- reuse Phase 12 persistence for schema validation, revisions and lifecycle metadata.

Exact normalized duplicates remain deterministic. Free-text non-duplicates do not receive an
autonomous local APPEND authorization from MiniLM or NLI. The Phase 16.2 evidence below showed that
those extra semantic gates add complexity without a sufficiently safe autonomous decision zone.

Representative cases:

```text
Existing: Marta trabaja en Airbus.
New:      Marta trabaja en Airbus.
=> exact duplicate -> NO_CHANGE

Existing: Marta trabaja en Airbus.
New:      Marta es empleada de Airbus.
=> Luna / medium with full authoritative note

Existing: Marta vive en Toulouse.
New:      Marta ahora vive en Lyon.
=> Luna / medium with full authoritative note

Existing: Marta vive en Toulouse.
New:      Marta ha empezado clases de piano.
=> Luna / medium decides bounded APPEND
```

### CREATE

A CREATE decision still does not give the model authority over identity, IDs, paths, lifecycle or
schema. Those remain deterministic Core responsibilities.

When free-text body composition is required, use the **same Luna / medium writer policy** rather than
creating a separate low/medium routing rule for CREATE versus UPDATE. `CREATE_BODY` remains a bounded
writer output; Core validates the result before persistence.

Never persist a partial note that silently drops free-text facts. Contextual unnamed entities such as
`la amiga de Marta` remain valid logical entities; a proper name is not required for creation
authorization.

## Phase 16.3 — selected bounded writer

Phase 16.3 selected the semantic writer policy from measured evidence:

```text
model              gpt-5.6-luna
reasoning effort   medium
context            full authoritative note
```

Use it for free-text CREATE/UPDATE reconciliation after deterministic structured work and the exact
normalized duplicate shortcut. Do not add conditions such as note-length routing, Luna-low for easy
cases, MiniLM/NLI writer filtering, or Terra/Sol writer fallbacks without new production evidence
showing a concrete need.

The writer produces bounded operations rather than rewriting an existing note blindly:

```text
NO_CHANGE
REPLACE exact old text -> new text
REMOVE exact old text
INSERT_AFTER exact anchor
APPEND
CREATE_BODY
```

Core must validate exact anchors/current revision/schema before persistence. Existing-note operations
that reference an `old` or `anchor` span must be grounded in the current authoritative body. A model
output never bypasses Core validation.

A writing skill controls presentation/organization, not whether a type may be created. There are no
per-type creation permission rules.

## Cost model

The selected common path is intentionally boring:

```text
planner                    existing interpretation call
identity resolution        local when exact; existing contextual fallback only if needed
structured mutations       deterministic
exact text duplicate       deterministic NO_CHANGE
remaining free text        one Luna / medium call with the full authoritative note
bounded application        deterministic Core validation + persistence
```

The matched difficult-case benchmark observed an average Luna-medium writer cost of about
`$0.00039712` per write, or approximately `$0.039712` per 100 writes and `$0.397120` per 1,000
writes at those observed input sizes. These are benchmark-derived figures, not workload forecasts.

## Deferred Phase 16 work

Still outside this checkpoint:

- production implementation of the selected bounded writer and operation application;
- explicit bulk write cardinality;
- wikilink/reference dependency materialization;
- soft-delete persistence (`status: deleted` direction already chosen);
- RequestPlan action orchestration (Phase 17);
- n8n integration.

## Evidence conclusion

The local semantic-gate experiments are complete for the current write architecture. MiniLM cosine
similarity had no useful safe autonomous APPEND threshold, NLI escalated too many independent facts,
and real MiniLM Top-3/Top-5 within-note retrieval dropped required long-note update evidence. Do not
continue tuning those layers merely to avoid the inexpensive Luna-medium writer call.

The historical evidence below is intentionally retained because it explains why the simpler final
architecture was selected.

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

**Historical assessment: NLI_PROMISING, not selected.** It materially improved semantic judgement
over cosine similarity, but the escalation rate and operational complexity did not justify a local
NLI layer once the later direct Luna-medium writer evidence was available. No further held-out NLI
validation is required for the selected initial write path. No NLI write gate is productionized.

### Phase 16.3 Luna writer evidence (2026-08-25)

This remains benchmark evidence only: no production writer, persistence, MiniLM gate, or write-path
integration changed. The original frozen 60-case full-note corpus has 59 PASS, 0 MINOR, and 1
MATERIAL_FAIL. U13 selected the exact subscription span, preserved the unrelated cooking fact, and
understood deletion, but encoded it as `REPLACE old -> ""` instead of `REMOVE old`. It is **A.
OPERATION_CONTRACT**, not a wrong target, information loss, or hallucination; empty `REPLACE`
remains invalid.

Historical raw evidence remains unchanged. It contains one malformed JSONL fragment and two
effective U45/FULL_NOTE records. Integrity metadata selects the first parseable result for semantic
evaluation, labels the later call a duplicate/recovery record, and charges both to actual spend.
Historical metadata said 60 planned FULL_NOTE calls although it intended 60 full + 12 reduced
calls. Future metadata records the per-strategy counts and total explicitly.

A separate frozen supplemental suite has twelve synthetic mutation cases. L01–L10 contain 50
factual units each and cover beginning, 25%, 50%, 75%, and near-end targets; update, duplicate,
independent/same-vocabulary independence, remove, multi-fact, mixed Markdown, and ES/FR are
included. VL01 is 2,783 words (buried final-third update); VL02 is 2,808 words
(related-but-independent append). Eight pre-frozen reduced contexts include both very-long notes.

Supplemental FULL_NOTE Luna results: 10 PASS, 0 MINOR, 2 MATERIAL_FAIL. The beginning and middle
updates, semantic duplicate, independent facts, same-vocabulary independence, multi-fact mutation,
mixed Markdown, ES/FR duplicate, and both very-long cases were faithful. L07 is another **A.
OPERATION_CONTRACT** error: it selected REMOVE and the right text but put its anchor in `text`
rather than `old`, leaving Core unable to validate/apply it. L03 is a dangerous **C.
SEMANTIC_RELATION** failure: with the employer fact near the end, Luna chose APPEND for a
conflicting Thales update, retaining contradictory current employment knowledge. All eight reduced
probes passed, but L03 has no reduced probe and the small sample does not establish a safe retrieval
layer.

Supplemental FULL_NOTE cost was $0.00497360 (18,256 input / 1,102 output tokens); reduced context
was $0.00196200 (3,984 input / 971 output), a 2.54× cost and 4.58× input-token reduction. The two
very-long full-note calls averaged $0.00093550. Across all actual Luna records, including the
historical duplicate: 93 calls, 52,395 input, 0 cached, 6,712 output, 1,532 reasoning tokens, and
$0.01853340 estimated spend.

**Interim low-reasoning assessment: LUNA_UNSAFE.** The long-note append/update confusion would have
justified testing a stronger policy. This assessment is retained as historical evidence and is
superseded by the later Luna-medium full-note comparison below.

### MiniLM-selected context follow-up (2026-08-25)

The previous 8/8 oracle-reduced calls remain an upper bound only: their fragments were frozen by a
reviewer, not retrieved. A new Luna-only within-one-resolved-note experiment used the existing local
FastEmbed multilingual MiniLM artifact. It embeds each planned fact independently against simple
Markdown body units; ranking projections prefix `Entity` and `Type`, while Luna receives only exact
authoritative source-order units. No expected operation, span, position, or review label enters the
retriever. TOP_3 was called for all twelve supplemental cases; TOP_5 was called only for L01, whose
required unit first ranked fourth.

MiniLM was weak at retaining several required update units: L01 rank 4, L02 rank 20, L03 rank 28,
L08 rank 15, and L09 rank 13. Thus L03's relevant Airbus fragment was absent from TOP_3 and TOP_5;
its TOP_3 APPEND is a **RETRIEVAL_FAIL**, not proof of a remaining Luna writer failure. TOP_5 L01
included the target and Luna correctly REPLACEd it. Required-target recall on the supplemental
update/remove/duplicate set was 4/9 at @1, 4/9 at @3, and 5/9 at @5. Independent and
same-vocabulary cases passed; L07 REMOVE, ES/FR duplicate, and both very-long cases passed when
their needed evidence was present.

MINILM_REDUCED cost for 13 actual Luna calls was $0.00263940. The experiment is therefore
**MINILM_RETRIEVAL_WEAK**. This rejects MiniLM as a Top-3/Top-5 within-note writer-context filter;
it does not change MiniLM's separate broad-retrieval role elsewhere in Odyssey.

### Luna/medium full-authoritative-note comparison (2026-08-25)

A separate frozen 15-case suite reran only difficult existing cases with the identical writer
prompt, schema, facts, evaluator, and full authoritative body; the sole provider-variable change
was Luna reasoning effort from low to medium. MiniLM/NLI filtering was not used. All 15 results
passed deterministic and semantic review: L03 returned the required exact REPLACE rather than
APPEND; L01/L02 long updates, L08 multi-fact, L07 REMOVE, L09 mixed Markdown, VL01/VL02,
negation, stopped habit, same-vocabulary independence, and ES/FR update remained faithful. There
were zero dangerous semantic and zero operation-contract failures. The explicit adjudication summary
is stored beside the raw run as `adjudication.json`.

For these matched cases, Luna/low averaged $0.00032992 and Luna/medium averaged $0.00039712
(1.20×). Medium cost is about $0.039712 per 100 writes and $0.397120 per 1,000 writes at observed
usage.

**Final selection: LUNA_MEDIUM_STRONG / USE_LUNA_MEDIUM_FULL_NOTE.** Human review accepts one
writer policy for Phase 16: full authoritative note → `gpt-5.6-luna` / medium → bounded operations →
Core validation → one persistence operation. Do not add MiniLM/NLI writer filtering, low/medium
routing, or Terra/Sol writer escalation in the initial implementation. Revisit model/routing
complexity only from real production evidence.
