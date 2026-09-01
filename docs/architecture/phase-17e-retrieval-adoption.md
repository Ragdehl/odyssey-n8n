# Phase 17E retrieval adoption decision

Status: **current decision subphase**

## Objective

Choose the smallest evidence-backed production retrieval contract for Odyssey before Phase 18. The
subphase decides whether to replace whole-note-only general-knowledge retrieval with the already
benchmarked deterministic Combined entity+fact fusion, and fixes the candidate-width and context
boundary that implementation must follow.

The decision must separate **local candidate breadth** from **strong-model context size**. A larger
MiniLM candidate pool does not by itself authorize sending the same number of units to Sol.

Canonical benchmark evidence is in
[Phase 17E retrieval benchmark](phase-17e-retrieval-benchmark.md), and the planner precondition is
closed in [Phase 17E planner semantic atomicity](phase-17e-planner-atomicity.md).

## Starting evidence

Combined is the leading retrieval strategy but remains unadopted at the start of this subphase.
The measured width sweep is:

| Combined raw width | Entity recall | ANY required fact | ALL required facts | Mean / median required-fact coverage |
|---:|---:|---:|---:|---:|
| 100 | 90.9% | 100% | 77.3% | 89.4% / 100% |
| 200 | 90.9% | 100% | 95.5% | 98.5% / 100% |
| 300 | 95.5% | 100% | 95.5% | 98.5% / 100% |
| 500 | 100% | 100% | 100% | 100% / 100% |

Top-400 was not measured as a reported aggregate cutoff. The only scale contextual case still
missing complete Combined evidence after Top-300 (`scale-100`) has its last required fact at raw rank
412, so Top-400 cannot reach 100% ALL-required-fact recall on the frozen corpus. The remaining
Top-400 aggregate metrics, especially entity recall, should be computed from the preserved ranked
outputs if available rather than guessed or rerun expensively without need.

The measured Combined Top-200 raw payload is approximately 4,054 tokens by the benchmark's chars/4
planning estimate. Top-500 is approximately 9,729 tokens. These are candidate payload measurements,
not a production context contract.

## Architecture challenge result

**PROCEED.** The observed problem is now narrow: choose the production retrieval unit and candidate
breadth from existing evidence without conflating candidate generation with final LLM context. Do not
introduce a new reranker, vector database, graph layer, second LLM, or speculative context-assembly
service. Reuse the current Core retrieval boundary and add only the minimum deterministic grouping or
hydration needed by the adopted contract.

## Decisions to close

1. **Retrieval strategy** — adopt Combined or retain whole-note-only. Combined is the default
   hypothesis because it materially improves multi-fact evidence completeness at compact raw payload.
2. **Candidate width** — explicitly compare 200, 300, 400, and 500. Do not choose 500 merely because
   it is the widest measured cutoff, and do not choose 200 merely because it is cheaper.
3. **Fusion contract** — prefer the fixed reciprocal-rank fusion already benchmarked unless a concrete
   correctness problem requires another rule.
4. **Context boundary** — define the smallest deterministic rule that converts the local candidate pool
   into grounded authoritative context. Candidate width and final Sol context size are separate limits.
5. **Insufficient-evidence behavior** — define how retrieval reports that the available evidence is not
   sufficient; retrieval remains evidence only and never gains write or identity authority.

## Acceptance criteria

- Reuse the frozen Phase 17E benchmark and planner evidence; do not repeat model selection.
- Compute the missing Top-400 aggregate metrics from preserved rankings if technically possible. If the
  required rankings were not preserved, run at most the smallest local MiniLM experiment necessary to
  obtain that cutoff and record why it was required.
- Compare Combined widths 200 / 300 / 400 / 500 on at least entity recall, ANY/ALL required-fact recall,
  required-fact coverage, raw candidate payload, and the difficult-case ranks already identified.
- Explain the marginal value of each width. In particular, distinguish the Top-200 -> Top-300 entity
  recall gain from the absence of an ALL-fact gain, and verify what Top-400 buys relative to Top-300
  before considering Top-500.
- Decide whether Combined is adopted. If adopted, freeze one production candidate width and the exact
  deterministic fusion rule.
- Define the final context boundary independently from candidate width. The contract must not imply that
  all raw candidates are sent to Sol.
- Preserve Markdown notes as source of truth. All selected context must be hydrated/validated against
  authoritative current notes before it can be exposed as grounded knowledge.
- Preserve current authority boundaries: semantic ranking is evidence only; it cannot authorize writes,
  bulk mutation, identity resolution, or schema changes.
- Produce an implementation-ready contract with no unresolved product/architecture decision required
  before the subsequent production retrieval PR.

## Out of scope

- Implementing Combined in production in this decision subphase.
- Phase 18 / n8n E2E work.
- Changing the MiniLM model or rerunning model selection.
- A vector database, graph retrieval, another LLM reranker, or a second planning pass.
- New schema, ontology, tags, application capabilities, or write semantics.
- Performance optimization beyond measurements required to choose the retrieval contract.
- Treating benchmark Top-K as the final number of units sent to Sol.

## Open decisions

- Adopt Combined or retain whole-note-only.
- Production Combined candidate width: 200, 300, 400, or 500.
- Exact minimum deterministic grouping/hydration rule between candidate retrieval and final grounded
  context.
- Final context budget/policy presented to the strong model; it must be independent from raw candidate
  width.
