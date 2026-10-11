# Full-message regression corpus v1

This folder is the immutable **synthetic** starting vault for testing Odyssey
Router → Temporal → ordinary Core planner → independent coverage → Writer →
Markdown readback and Notes links. It is not user knowledge.

- `manifest.json` records the version, accepted 27-message design path,
  fixed Paris test clock and the identities/types of the 13 canonical Notes.
- `vault/*.md` are genuine, schema-valid Odyssey Markdown notes for fictional
  people, a test family, two projects, a vehicle, a house and a document.
- `tests/runtime/test_full_message_corpus_regression.py` copies the **same
  committed snapshot into a fresh temporary directory for each test**.
  No test writes back to these files; a second test never inherits mutations.
- The 27 original source messages and source-only semantic oracles live in
  `benchmarks/application_router/fact_units_v2.design.json`. They are NOT
  rewritten here, and no Core fact ownership is inferred from candidate order.
- The 27 authentic saved GPT-6 Router v3 outputs replay offline through the
  genuine Router adapter against a freshly validated test vault, including the
  known F27 source-provenance failure, which must remain visibly fail-closed.
- Authentic prior whole-message GPT-5.6 Core model responses for F09 and F10
  replay into the existing Core planner and the ordinary Markdown Writer and
  verify persisted facts, canonical links and backlinks. Their independent
  Core coverage proposals are explicit **test oracles**, not a model success
  claim or a product fallback.
- Additional previously committed variable-cardinality end-to-end tests
  exercise 1→N, N→1 and N↔M candidate/fact relationships with independent
  simulated SDK outputs. These remain separate from real-provider evidence.

## Adding regressions

Keep historical cases fixed. Add new user-message failure sentinels to a
versioned successor of the design corpus; when the regression depends on
existing knowledge, add corresponding synthetic canonical Notes to a
versioned successor of this snapshot. Define expected **outcomes**, source
evidence and unauthorized-write negative assertions. Preserve old negative
cases when making a generalized architecture fix. Re-run the complete
fixture-based provider-free suite before any live API test.

## Evidence boundary

A green 27-case **Router replay** is NOT a 27-case live end-to-end pass:
most historical messages have no saved compatible Core/Temporal/reviewer
provider outputs. Only the recorded Core cases and the separately executed
real-provider one-message end-to-end smoke have complete persistence
observations. To run all 27 with current providers, the test runner must use
a disposable copy of these notes, record each stage's actual model result,
call the ordinary Core guards and Writer, audit physical Markdown and
backlinks, and produce a case-by-case pass/defer/fail report. No unsafe
automatic guessed source-to-fact mapping may turn a failed test green.

Fresh 27-message four-model execution exceeds the previously approved
USD 0.07 aggregate provider cap (about USD 0.0564021 already estimated spent).
Obtain and enforce a newly approved cumulative cap before those billable
runs; do not silently retry previously billed requests.
