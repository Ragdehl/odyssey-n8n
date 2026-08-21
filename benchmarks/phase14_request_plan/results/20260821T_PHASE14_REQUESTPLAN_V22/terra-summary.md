# Phase 14 RequestPlan v2.2 — Terra/low stage

This is a derived report. Raw provider evidence remains append-only in
[`raw_results.jsonl`](raw_results.jsonl); frozen benchmark inputs were not modified.

## Execution

- Benchmark: v2.2.0; model `gpt-5.6-terra`; reasoning `low`
- Logical requests: 24 (all cases, repetition 1)
- API attempts: 48 (24 initial, 24 explicitly permitted retries)
- Effective results: 19 successful, 5 unresolved transport failures
- Failed logical cases after retry: B01, B03, B05, N03, A02
- Sol and Luna: not executed; repetitions 2–4: not executed

Frozen-input SHA-256 hashes are recorded in [`metadata.json`](metadata.json).

## Quality totals

Counts below cover the 19 effective successful model responses; transport failures
are reported separately and are not quality failures.

| Status | Count |
|---|---:|
| 🟢 PASS | 17 |
| 🟡 HUMAN REVIEW | 0 |
| 🟠 MINOR | 0 |
| 🔴 MAJOR | 0 |
| 🟥 CRITICAL | 2 |

## Non-PASS cases

| Test | Request | Status | Generated RequestPlan / finding | Difference from oracle |
|---|---|---|---|---|
| S02 | ¿Qué entradas de diario escribí ayer sobre los niños? | CRITICAL | One retrieve action: query `entradas de diario sobre los niños`, type `journal_entry`, no tags, filter `entry_date eq 2026-08-19`. Findings: unexpected hard filter; missing safe filter; missing retrieval coverage; extra branch diagnostic. | Terra used unsupported semantic date field `entry_date` and omitted the oracle’s safe `created_at` constraint, excluding valid candidates. The extra-branch diagnostic is evaluator-derived; the actual output had one branch. |
| S03 | ¿Qué ideas sobre Odyssey tengo marcadas para revisar? | CRITICAL | One retrieve action: query `Odyssey`, type `concept`, required tag `review`, no filters. Findings: type restriction; missing required tag; missing retrieval coverage; extra branch diagnostic. | Terra narrowed the requested candidate set to `concept` and omitted the requested review tag, rather than preserving the oracle’s broader safe retrieval. The extra-branch diagnostic is evaluator-derived; the actual output had one branch. |

There were no HUMAN REVIEW diagnostics in the effective successful results, so no
manual wording reclassification was required.

## Deterministic safety verdict

- Candidate-set / side-effect CRITICAL failure: **Yes** — S02 and S03.
- False hard filter that could eliminate valid requested notes: **Yes** — S02 (`entry_date`).
- Entire requested retrieval branch omitted: **Yes** — evaluator reports missing coverage for S02 and S03.
- Unrequested `CreateNoteAction`: **No**.

The “extra retrieval branch” findings on S02/S03 are conservative evaluator
diagnostics and do not describe an extra action in the generated plans.

## Tokens, cache, latency, and cost

Successful responses only (failed transport attempts had no provider usage):

- Input tokens: 40,871 total, including 38,376 cached-input tokens and 2,132 cache-write tokens
- Output tokens: 1,429; reasoning tokens: 287
- Cache writes: 1 request, 2,132 tokens
- Cached reads: 18 requests, 38,376 tokens
- Neither cache counter: 0 requests
- Pattern: first successful request wrote the stable prefix; the next 18 successful requests read it. Five unresolved failures have no provider counters.
- Estimated recorded cost: **$0.038599**
- Approximate no-caching counterfactual for the successful requests: **$0.123613**
- Mean latency: 2.394 s; median latency: 2.093 s

The counterfactual is calculated from recorded total input/output counters using
ordinary input pricing and is only for the 19 successful requests.

## Assessment

RequestPlan v2 appears to have fixed the principal v1 contract weakness for the
successful cases: multi-action cases, OR branches, mixed create/retrieve, compound
create, and create-only cases passed. It did not eliminate false-hard-filter and
over-narrowing failures in S02/S03, so Terra is not safety-clean on this stage.

With five unresolved API failures and two deterministic CRITICAL quality failures,
the evidence does not yet support Terra as the production choice. A Sol comparison
is still warranted after human review, but this report does not execute or imply
approval to execute it.
