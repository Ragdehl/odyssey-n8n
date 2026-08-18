# Phase 11B.1c large-vault retrieval stress result

## Frozen setup

The deterministic generator materialized 1,000 schema-valid Markdown notes in a temporary vault:
30 frozen targets plus 970 adversarial distractors across every current canonical note type. The
distractors repeatedly overlap on people and family roles, Carrefour and other stores, Odyssey and
Atlas, maps, projects, AI, banks, partners, locations, and nearby concepts. The committed fixture
contains 40 expected-target queries frozen before measurement, not the generated Markdown corpus.

Queries cover English (14), Spanish (14), and French (12), with literal (9), alias (6), semantic
paraphrase (13), synonym mismatch (7), and deliberately polysemous (5) cases. Current schema has no
place type, so Place du Capitole is represented as a concept explicitly describing a location.

The baseline is the unchanged Phase 10 FastEmbed multilingual MiniLM retriever. The one experimental
hybrid unions the full type-filtered dense ranking, name/alias token overlap, and same-language
NLTK WordNet/OMW 1.4 lemma overlap over note projections using reciprocal-rank fusion (`k=60`). It
returns candidates only and makes no identity decision.

## Recall

| Method | Recall@1 | Recall@3 | Recall@5 | Recall@10 |
| --- | ---: | ---: | ---: | ---: |
| Current dense | 72.5% | 75.0% | 77.5% | 77.5% |
| Experimental hybrid | 62.5% | 72.5% | 80.0% | 80.0% |

| Slice | Dense @1/@3/@5/@10 | Hybrid @1/@3/@5/@10 |
| --- | --- | --- |
| English | 71.4 / 78.6 / 78.6 / 78.6% | 57.1 / 71.4 / 71.4 / 71.4% |
| Spanish | 71.4 / 71.4 / 71.4 / 71.4% | 57.1 / 71.4 / 85.7 / 85.7% |
| French | 75.0 / 75.0 / 83.3 / 83.3% | 75.0 / 75.0 / 83.3 / 83.3% |
| Literal | 77.8 / 77.8 / 77.8 / 77.8% | 100 / 100 / 100 / 100% |
| Alias | 100 / 100 / 100 / 100% | 100 / 100 / 100 / 100% |
| Semantic paraphrase | 69.2 / 76.9 / 76.9 / 76.9% | 53.8 / 61.5 / 76.9 / 76.9% |
| Synonym mismatch | 28.6 / 28.6 / 42.9 / 42.9% | 14.3 / 42.9 / 57.1 / 57.1% |
| Polysemy | 100 / 100 / 100 / 100% | 40.0 / 60.0 / 60.0 / 60.0% |
| Literal/alias wording | 86.7 / 86.7 / 86.7 / 86.7% | 100 / 100 / 100 / 100% |
| Semantic/synonym mismatch | 64.0 / 68.0 / 72.0 / 72.0% | 40.0 / 56.0 / 68.0 / 68.0% |

Dense Top-5 misses were `es-wife-mujer`, `es-wife-esposa`, `fr-wife-femme`, `en-wife-spouse`,
`es-colleague`, `en-project-literal`, `en-project-atlas`, `fr-project-ai`, and
`es-concept-atomic`. The hybrid rescued `fr-wife-femme`, `es-colleague`, both literal Atlas/Odyssey
project cases, `fr-project-ai`, and `es-concept-atomic`. It introduced new Top-5 misses for
`fr-mother`, `en-friend`, `en-store-polysemy`, `fr-project-semantic`, and `en-project-plan`.

## Lexical resource and operational evidence

NLTK 3.9.2 itself occupied about 19 MB in the isolated environment. The required WordNet and OMW
1.4 data were about 11 MB and 26 MB compressed respectively; the NLTK catalog reports OMW at about
96.8 MB expanded. OMW has mixed per-language licensing and must be installed separately. Normal
production use must never download these resources implicitly.

Coverage was materially uneven. French `femme` and `épouse` share useful lemmas. Spanish `mujer`
and `esposa` did not, and English `wife` and `spouse` did not. Expanding every sense of `partner`,
`bank`, `store`, and `project` produced unrelated evidence and caused ranking regressions.

On the ARM64 benchmark host, the warm local corpus creation plus embedding/index build took about
59.9 seconds. Median dense query latency was 24.5 ms; median hybrid latency was 28.6 ms. The SQLite
index was 2.15 MB. Rough process peak RSS was 1.80 GiB, including Python, FastEmbed/ONNX, the model,
the temporary corpus build, and loaded NLTK resources; it is a conservative process-level figure,
not incremental index memory.

## Decision

**REJECT/DEFER.** The hybrid improves overall Recall@5 and Recall@10 by only one net case (2.5
percentage points), lowers Recall@1 and Recall@3, introduces five Top-5 regressions, misses four of
the six required spouse-wording cases, and adds disproportionate resource/deployment/licensing
complexity. Phase 10 production code and dependencies remain unchanged. The result reinforces that
retrieval supplies candidates only; contextual reasoning and deterministic Core validation retain
all identity authority.

## Final bounded reranking viability test

The same 1,000-note corpus and the same 40 frozen queries were reused without modification. The
current exact primary-name/alias lookup uniquely short-circuits 15 queries, leaving 25
**contextual-only queries** for the production semantic-retrieval path.

### Broad unchanged MiniLM retrieval

| Set | @1 | @3 | @5 | @10 | @20 | @50 | @100 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All 40 | 72.5% | 75.0% | 77.5% | 77.5% | 87.5% | 92.5% | 100% |
| Contextual-only 25 | 64.0% | 68.0% | 72.0% | 72.0% | 80.0% | 88.0% | 100% |

All-query category slices at @5/@10/@20/@50/@100 were: literal 77.8/77.8/100/100/100%, alias
100/100/100/100/100%, semantic paraphrase 76.9/76.9/92.3/100/100%, and synonym mismatch
42.9/42.9/42.9/57.1/100%. Contextual-only @5/@50/@100 by language was EN 85.7/100/100%,
ES 55.6/77.8/100%, and FR 77.8/88.9/100%.

Every contextual-only Top-5 miss still had the expected note in the broad ranking:

| Query | MiniLM expected rank |
| --- | ---: |
| `es-wife-mujer` | 93 |
| `es-wife-esposa` | 54 |
| `fr-wife-femme` | 85 |
| `en-wife-spouse` | 23 |
| `es-colleague` | 17 |
| `fr-project-ai` | 13 |
| `es-concept-atomic` | 48 |

Thus this fixture shows a ranking problem for Top-5, not a broad-retrieval failure at Top-100,
although ES remains materially weaker at Top-50.

### mMARCO candidate-only reranking

The exact Phase 11A artifact was reused: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, ONNX
`model_qint8_arm64.onnx` plus tokenizer, 135,702,677 bytes total (118,620,017-byte model and
17,082,660-byte tokenizer). It was run only as a sorter over the existing semantic projection;
its scores were not treated as confidence and it made no identity decision.

| Pipeline | Contextual-only @1/@3/@5 | All 40 @1/@3/@5 |
| --- | --- | --- |
| MiniLM Top-20 → rerank → Top-5 | 68.0 / 72.0 / 72.0% | 67.5 / 72.5 / 75.0% |
| MiniLM Top-50 → rerank → Top-5 | 60.0 / 68.0 / 72.0% | 67.5 / 72.5 / 75.0% |
| MiniLM Top-100 → rerank → Top-5 | 68.0 / 68.0 / 72.0% | 72.5 / 72.5 / 75.0% |

The contextual-only Top-5 result did not improve over MiniLM's 72.0%. All three pipelines missed
`es-wife-mujer`, `es-wife-esposa`, `fr-wife-femme`, `fr-wife-epouse`, `en-wife-wife`,
`en-wife-spouse`, and `es-concept-atomic`. Contextual-only @5 by language was unchanged across
the three widths: EN 71.4%, ES 66.7%, FR 77.8%.

### Raspberry Pi performance and conclusion

On the ARM64 Raspberry Pi runtime, MiniLM median query latency was 23.4 ms and index build was
about 60.3 s. Cross-Encoder model load was 1.16–1.23 s; reranking medians were 680 ms, 1.81 s,
and 3.58 s for Top-20, Top-50, and Top-100. Peak process RSS was approximately 2.17, 2.34, and
2.48 GiB respectively. No swap use was reported for the exact artifact in the retained Phase 11A
ARM64 runtime metadata; no production model was installed or changed by this experiment.

**FAIL / ARCHITECTURE CONCERN.** Broad MiniLM retrieval reaches 100% Recall@100 on this fixture,
but the Cross-Encoder cannot recover contextual Top-5 recall and introduces ranking regressions.
The Top-100 path also has a high memory footprint for interactive Raspberry Pi use. Keep the
current production pipeline and do not adopt this reranker. This bounded experiment is complete;
no further retrieval approach is proposed here.
