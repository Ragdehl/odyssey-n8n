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
