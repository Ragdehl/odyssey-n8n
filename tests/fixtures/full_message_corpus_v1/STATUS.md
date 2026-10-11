# 27-message corpus checkpoint — 2026-10-11

**Original corpus:** `benchmarks/application_router/fact_units_v2.design.json`
contains F01–F27, unchanged. **Canonical synthetic test Notes:** 13 valid
Markdown files at `tests/fixtures/full_message_corpus_v1/vault/`. Each test
copies the entire fixture into its own disposable vault and uses a fixed
2026-10-04 Europe/Paris clock. No user knowledge, active DEV/PROD workflow,
live chat, or new service is touched.

## Evidence per stage

| Cases | Historical authentic GPT-6 Router reply | Core/provider state | Markdown outcomes |
| --- | --- | --- | --- |
| F01–F08 | Replayed, source-valid, dependencies valid | No matching complete saved Core + Temporal + review chain | Full E2E not yet tested live |
| F09 | Replayed, source-valid | Authentic previous whole-message GPT-5.6 plan; explicit synthetic coverage reply | **PASS**: two existing Person Notes updated, atomic readback verified |
| F10 | Replayed, source-valid | Authentic previous whole-message GPT-5.6 plan; explicit synthetic coverage reply | **PASS**: one linked fact, canonical identity link and backlink verified |
| F11 | Replayed, source-valid | Fresh GPT-6 Router + GPT-6 Temporal completed. Core call **not made**: budget reservation rejected | Zero writes, **INCOMPLETE** (budget, not semantic failure) |
| F12–F26 | Replayed, source-valid, dependencies valid | No matching complete saved Core + Temporal + review chain | Full E2E not yet tested live |
| F27 | Replayed, source-valid JSON | Saved Router subject-inheritance trace rejected (implicit grammatical subject lacks verified predecessor evidence) | Zero writes, **KNOWN OPEN PROVENANCE DEFECT** |

Every F01–F27 Router response originates from previous actual GPT-6 calls
(frozen receipts), not current live execution. The F09/F10 Planner outputs
are likewise saved *real* GPT-5.6 provider responses, but their graph
reviewer responses are **injected deterministic test oracles**. Neither
counts as fresh all-four-provider execution. The earlier one-message
four-provider live smoke (not one of these F01–F27 messages) already
verified a real persisted canonical Day fact; it remains separate.

The new automatic model-review/Core coverage gate is tested with
independent generated 1→N, N→1 and mixed edges and negative cases.
For two semantically identical Person fact texts, swapping the source
owner candidate's **Core ordinal** now has a permanent negative sentinel:
ordinary Core source-subject/target checks reject the wrong pairing with
zero writes. This does not rely on case IDs or person's names in product code.

## Live-cost boundary

The previously approved cumulative USD 0.07 cap remains unchanged.
Earlier estimated spend was USD 0.0564021. F11's real Router and Temporal
cost approximately USD 0.0003639 total, taking estimated cumulative spend to
**USD 0.056766**. The unchanged Core model request requires a worst-case
precall reservation of ~USD 0.0145162, greater than the remaining
USD 0.013234. Core correctly refused the call **before sending it**.
That is why F11 is marked incomplete, not a failed language interpretation.
The generic corpus runner now refuses to start an incomplete four-model
attempt if the available budget cannot accommodate conservative headroom.

Remaining work before calling 27/27 end-to-end: a **new explicitly approved
bounded provider budget** for the complete matrix; classify and review
each actual stage/plan/graph response; re-run valid cases against clean
seeded Notes and inspect canonical facts/links; preserve failures as
general regression sentinels. The full corpus suite is prepared and
offline tests require **zero** provider credentials. Any literal date-less
messages or ambiguous source roles must be reviewed against the existing
Temporal/Router/Core contract; do not invent missing date evidence or
bypass coverage to force a green result.
