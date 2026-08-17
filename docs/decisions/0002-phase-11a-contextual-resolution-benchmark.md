# ADR 0002: Phase 11A contextual-resolution benchmark

- Status: Proposed; human technology decision required
- Date: 2026-08-17

## Context

Phase 10 supplies ranked candidates but cannot decide whether a contextual reference uniquely
identifies one of them. Phase 11A compared four local decision strategies on ARM64 before any Phase
11B production implementation. A false `RESOLVED` was treated as the most serious failure.

The synthetic benchmark freezes 10 calibration cases and 51 untouched evaluation cases over 20
notes. English, Spanish, and French each contain 16 evaluation cases with the same outcome mix;
three Catalan cases are non-blocking. Cases include same-name and alias collisions, relationships,
strong distractors, misleading overlap, negative evidence, context-dependent answers, and absent
entities. Every method received the same Phase 10 Top-5 candidate sets. Phase 10 retrieved the
expected note for all 22 `RESOLVED` evaluation cases, so none of the measured resolver errors was a
Phase 10 retrieval miss.

## Measured results

Primary comparison below excludes the three non-blocking Catalan cases. Score thresholds and
margins were selected only on calibration cases. The evaluation split was not used for tuning.

| Method | False RESOLVED | Correct R / A / U | Coverage | Accuracy when resolved | Overall accuracy | Mean latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cosine score policy | 8/48 (16.7%) | 10 / 7 / 4 | 37.5% | 55.6% | 43.8% | ~0.00003 s decision-only |
| mMARCO Cross-Encoder policy | 7/48 (14.6%) | 15 / 4 / 5 | 45.8% | 68.2% | 50.0% | 0.133 s |
| Qwen3 0.6B Q8_0 | 29/48 (60.4%) | 17 / 0 / 2 | 95.8% | 37.0% | 39.6% | 3.75 s |
| Llama 3.2 1B Instruct Q4_K_M | 34/48 (70.8%) | 14 / 0 / 0 | 100% | 29.2% | 29.2% | 6.59 s |

Both LLMs produced identical decisions across two runs, but both overwhelmingly selected a
candidate instead of abstaining. The Cross-Encoder was the strongest measured method overall and
resolved difficult contextual cases well, yet seven false links still violate the safety priority.
All methods struggled with superficially related absent entities. Score policies also confused
`AMBIGUOUS` with `UNRESOLVED`, especially for same-name French cases.

## Runtime and reproducibility

Runs used Python 3.13.5, FastEmbed 0.7.3, ONNX Runtime 1.28.0, Tokenizers 0.23.1, and llama.cpp
b10218 (`de699957b`) on AArch64. The LLM server used four generation/batch threads, a 4096-token
context, one slot, seed 0, temperature 0, reasoning disabled, prompt caching disabled, and structured
JSON output with a 40-token maximum. No chain-of-thought was requested or persisted.

| Artifact | Disk | Load | Peak server RSS | Swap observation | Output speed |
| --- | ---: | ---: | ---: | ---: | ---: |
| mMARCO Cross-Encoder ONNX + tokenizer | 135.7 MB | included in 8.14 s full method | n/a; 707 MB peak runner including Phase 10 | none | n/a |
| Qwen3 0.6B Q8_0 GGUF | 639.4 MB | 11.14 s | 2.37 GiB | 1.20 GiB process swap at peak workload | 14.1 tokens/s |
| Llama 3.2 1B Q4_K_M GGUF | 1.23 GB | 22.60 s | 2.20 GiB | ~1.5 MiB process swap | 12.6 tokens/s |

Qwen's swap measurement includes concurrent Phase 10 candidate construction and represents observed
system impact, not model weights alone. Llama began after residual host swap use from the prior run;
its own recorded process swap remained small. Raw per-case results, token counts, memory snapshots,
timings, categories, language metrics, and exact artifact identities are durably stored under
`/data/odyssey/runtime/phase11a-benchmark/results/`. The version-controlled dataset and runner in
`benchmarks/` reproduce the comparison when the model artifacts are available.

## Benchmark artifact cleanup

The Phase 11A runtime directory used 2,306,901,405 apparent bytes at its measured peak (about
2.15 GiB), including the newly materialized Phase 10 embedding cache. After results and this record
were persisted, the losing benchmark-only Cross-Encoder, both GGUFs, llama.cpp binaries, and the
llama.cpp archive were removed. The retained results and Phase 10 MiniLM cache use 252,413,481
apparent bytes (about 241 MiB), a reduction of 2,054,487,924 bytes (about 1.91 GiB).

The Phase 10 dataset and runner in Git were retained: they are decision evidence, not disposable
runtime artifacts. No clearly Odyssey-owned obsolete Phase 10 index or comparison cache was found.
Artifacts of uncertain ownership were not deleted.

## Recommendation

Do not use any tested method as the standalone production Phase 11 resolver. If future work is
approved, the Cross-Encoder is the only measured component worth carrying forward for investigation,
but it needs an additional conservative decision design validated on new held-out cases. Raw cosine
and both tested small LLMs should be rejected as identity decision-makers for this contract.

This is evidence, not the final production technology choice. Phase 11B is not implemented here.

## Consequences

Odyssey remains without a contextual resolver and continues to preserve Phase 10's candidate-only
boundary. That is safer than adopting a method that creates false links. A human must decide whether
to investigate a more conservative Cross-Encoder-based design, test a different approach, or defer
contextual resolution.
