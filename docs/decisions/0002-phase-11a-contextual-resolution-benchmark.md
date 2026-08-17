# ADR 0002: Phase 11A contextual-resolution benchmark

- Status: Phase 11A architecture direction approved; Phase 11B decisions pending
- Date: 2026-08-17

## Context

Phase 10 supplies ranked candidates but cannot decide whether a contextual reference uniquely
identifies one of them. Phase 11A compared local decision strategies on ARM64, then recorded manual
strong-reasoner feasibility experiments, before any Phase 11B implementation. A false `RESOLVED` was
treated as the most serious failure.

## Phase 11A.1: local benchmark

The synthetic benchmark freezes 10 calibration cases and 51 untouched evaluation cases over 20
notes. English, Spanish, and French each contain 16 evaluation cases with the same outcome mix;
three Catalan cases are non-blocking. Cases include same-name and alias collisions, relationships,
strong distractors, misleading overlap, negative evidence, context-dependent answers, and absent
entities. Every method received the same Phase 10 Top-5 candidate sets. Phase 10 retrieved the
expected note for all 22 `RESOLVED` evaluation cases, so none of the measured resolver errors was a
Phase 10 retrieval miss.

The primary comparison excludes the three non-blocking Catalan cases. Score thresholds and margins
were selected only on calibration cases. The evaluation split was not used for tuning.

| Method | False RESOLVED | Correct R / A / U | Coverage | Accuracy when resolved | Overall accuracy | Mean latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cosine score policy | 8/48 (16.7%) | 10 / 7 / 4 | 37.5% | 55.6% | 43.8% | ~0.00003 s decision-only |
| mMARCO Cross-Encoder policy | 7/48 (14.6%) | 15 / 4 / 5 | 45.8% | 68.2% | 50.0% | 0.133 s |
| Qwen3 0.6B Q8_0 | 29/48 (60.4%) | 17 / 0 / 2 | 95.8% | 37.0% | 39.6% | 3.75 s |
| Llama 3.2 1B Instruct Q4_K_M | 34/48 (70.8%) | 14 / 0 / 0 | 100% | 29.2% | 29.2% | 6.59 s |

Both small local LLMs produced identical decisions across two runs, but both overwhelmingly selected
a candidate instead of abstaining. The Cross-Encoder was the strongest measured method overall and
resolved difficult contextual cases well, yet seven false links still violate the safety priority.
All methods struggled with superficially related absent entities. Score policies also confused
`AMBIGUOUS` with `UNRESOLVED`, especially for same-name French cases.

### Runtime and reproducibility

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
its own recorded process swap remained small.

The compact version-controlled [local result record](../../benchmarks/phase11a_local_results.md)
preserves the frozen ground truth and every method's per-case decision and selected ID. The dataset
and runner in `benchmarks/` reproduce the comparison when model artifacts are available. Detailed
runtime JSON was stored under `/data/odyssey/runtime/phase11a-benchmark/results/` but is not required
to inspect the identity outcomes.

### Benchmark artifact cleanup

The Phase 11A runtime directory used 2,306,901,405 apparent bytes at its measured peak (about
2.15 GiB), including the newly materialized Phase 10 embedding cache. After results and this record
were persisted, the losing benchmark-only Cross-Encoder, both GGUFs, llama.cpp binaries, and the
llama.cpp archive were removed. The retained results and Phase 10 MiniLM cache use 252,413,481
apparent bytes (about 241 MiB), a reduction of 2,054,487,924 bytes (about 1.91 GiB).

The Phase 10 dataset and runner in Git were retained: they are decision evidence, not disposable
runtime artifacts. No clearly Odyssey-owned obsolete Phase 10 index or comparison cache was found.
Artifacts of uncertain ownership were not deleted.

## Phase 11A.2: strong-reasoner feasibility follow-up

A later manual blind experiment used the same 20 synthetic notes, conservative decision contract,
10 labelled calibration/few-shot examples, and 48 blocking evaluation cases. Two independent temporary
ChatGPT conversations had no Odyssey conversation memory or context. Both returned identical decisions
on all 48 cases (48/48 consistency).

Against labels frozen before those answers were seen, the result was 21/21 correct `RESOLVED`, 14/15
correct `AMBIGUOUS`, 12/12 correct `UNRESOLVED`, 1/48 false `RESOLVED`, 47/48 overall, and 21/22
(95.5%) accuracy when resolved.

The sole error, E13 (`en-toulouse-supermarket`, “the supermarket in Toulouse”), is a disputed label.
ChatGPT selected `carrefour-market-capitole`, the only note explicitly described as being in Toulouse;
the frozen label treated the Balma and Labège stores as plausible and expected `AMBIGUOUS`. Odyssey
preserves the historical label and official score rather than relabelling after seeing the answer,
while recording the substantive disagreement.

## Phase 11A.3: frozen fresh adversarial holdout

The prompt, decision contract, and calibration examples were frozen before evaluating 42 entirely new
adversarial cases: 14 expected `RESOLVED`, 14 `AMBIGUOUS`, and 14 `UNRESOLVED`. They emphasized strong
distractors, partial matches, negative evidence, name collisions, plausible absent entities, and
context-dependent identity.

The result was 14/14 correct `RESOLVED`, 14/14 correct `AMBIGUOUS`, and 14/14 correct `UNRESOLVED`:
42/42 semantic accuracy with 0/42 false `RESOLVED`. Decisions and order were correct, but the response
omitted the requested `case_id` property. This is direct evidence that production Core must validate
model output schema rather than trust formatting.

The manual transcript and 42 case texts were not generated by the repository runner and are not
part of the local benchmark runner. The supplied experiment payload is now preserved in the
version-controlled [strong-reasoner evidence](../../benchmarks/phase11a_strong_reasoner_results.md),
including frozen labels, both Phase 11A.2 run decisions, the complete Phase 11A.3 cases, the raw
schema-noncompliant response, and its position-based normalization.

## Combined interpretation

Across 90 unique blocking cases, the official frozen-label score is 89/90: 35/35 correct `RESOLVED`,
28/29 correct `AMBIGUOUS`, 26/26 correct `UNRESOLVED`, and 1/90 false `RESOLVED`. The only false
`RESOLVED` is disputed E13. The independent repeat of the first 48 cases strengthens the feasibility
evidence, but does not validate every strong LLM or any particular API model.

The narrow conclusion is that a sufficiently capable contextual reasoner appears able to perform this
task reliably under the tested contract, whereas the tested small local models could not. The local
benchmark conclusions remain: cosine is insufficient; the measured Cross-Encoder is unsafe as a
standalone resolver; and Qwen3 0.6B and Llama 3.2 1B are unsafe as standalone resolvers. The
Cross-Encoder remains an interesting possible component, but Phase 10 retrieval already performed well,
so there is no demonstrated need to insert it before a strong reasoner.

## Approved Phase 11 architecture direction

The human has approved this architecture direction:

```text
exact resolution
      |
      v
Phase 10 semantic Top-N candidate retrieval
      |
      v
strong contextual reasoner
      |
      v
RESOLVED / AMBIGUOUS / UNRESOLVED
      |
      v
deterministic Odyssey Core validation
```

Phase 10 supplies candidate evidence, never identity confidence. The reasoner supplies a contextual
decision; Odyssey Core remains authoritative for the contract. Core must reject malformed output,
reject a selected ID outside the supplied candidate set, and otherwise fail closed. `AMBIGUOUS` and
`UNRESOLVED` remain legitimate outcomes. Frequent human-in-the-loop interaction is not designed into
Phase 11; clarification may remain an exceptional future fallback.

This approval is architectural only. It does not select OpenAI, a model or other provider, an API
endpoint, privacy or retention configuration, anonymization implementation, pricing strategy, a
fallback model, or retry policy. Those provider and implementation decisions remain Phase 11B work.

If Phase 11B uses a cloud reasoner, it should minimize evidence sent externally. Anonymization or
pseudonymization may be considered where useful. Provider, model, API, privacy guarantees, cost, and
fallback strategy remain Phase 11B decisions and are not frozen here.

## Decision and consequences

Do not use cosine, the tested Cross-Encoder, Qwen3 0.6B, or Llama 3.2 1B as a standalone production
resolver. Carry the approved strong contextual-reasoner architecture into Phase 11B with deterministic
fail-closed validation. This is feasibility evidence and architecture approval, not a provider or
production technology selection. Phase 11B is not implemented here.

Odyssey remains without a contextual resolver and preserves Phase 10's candidate-only boundary. Phase
11B provider and implementation decisions remain pending. Additional context such as recent
conversation/entities, the active project, recent notes, and existing links may be future evidence
sources, but are not Phase 11A implementation or frozen Phase 11B requirements.
