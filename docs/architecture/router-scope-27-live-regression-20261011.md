# Odyssey — Router scope: 25 remaining real-model regressions (2026-10-11)

**Status:** experimental branch-only evidence. **NOT** a DEV/PROD rollout,
nor semantic correctness certification. No actual personal user Notes were
accessed; every attempt used its own clone of the committed 13-note synthetic
canonical Markdown vault. Inputs: F01–F27 in
`benchmarks/application_router/fact_units_v2.design.json`, excluding
previously tested F09/F13.

- **25/25** additional cases attempted with real GPT-6 Router and, where
  reached, real GPT-6 Temporal, GPT-5.6 Core ordinary Planner and independent
  GPT-5.6 Core fact reviewer, normal Core Writer and physical Markdown readback.
- **3 complete:** F04, F11, F23.
- **2 partial:** F01, F14. These are NOT complete-source successes.
- **20 not complete:** 19 returned FAILED/NEEDS_ATTENTION status and F05
  raised a safe source-dependency compiler error.
- Additional new provider estimate: **USD 0.0702060**, cumulative estimated
  spend **USD 0.2101866 / 0.25 approved**; unused authorization USD
  0.0398134. Those estimates are not actual provider billing statements.
- **Every real provider response** (including genuinely truncated Temporal
  JSON) has been saved unchanged in
  `benchmarks/application_router/scoped_routing_v1/Fxx.json`. The permanent
  offline replay is `tests/runtime/test_scoped_route_remaining_corpus_replay.py`,
  and existing real-model F09/F13 replays are in
  `tests/runtime/test_scoped_route_recorded_real_replay.py`.
- All pending/failed cases are first-class regression outcomes. An offline
  test that faithfully reproduces a failure is **not** a passed product
  acceptance criterion.

## Critical architecture contract gap: source grouping

The v1 Router proposes multiple source candidates, but the current
`compile_candidate_route_bundle` fuses any candidates with overlapping
source anchors or a shared/inherited role into a single original-text route.
From these 25 genuine Router outputs, 24 compile structurally; **17 of the
24 have multiple candidates compressed into a single route containing the
whole current user message**. This conflicts with the user's explicit
agreement that Router dispatches separate fact-bearing fragments plus
typed, source-grounded dependencies; Temporal and Core must not be asked to
re-plan sibling facts simply because two statements share a date, subject,
predicate or order relation. Examples include:

- F06: `Hoy vi a Ana y compré pan.` → two Router candidate facts but one
  Core request with the entire message. Required: two scoped units with
  shared `Hoy` evidence; do not copy/forge the date as source text.
- F02/F03/F07/F08/F15/F20/F21/F23/F24/F25 similarly contain multiple
  candidates that currently collapse into one route.
- Some groupings are semantically one indivisible operation (a mutual
  relationship F10, one shared purchase event F11, or the two shared-predicate
  source mentions F09), but this must be a deliberate source-scoped decision
  rather than automatic merging on *any* shared text.
- F05 real Router output also failed the inherited-role provenance checker.
  This refusal prevents a guessed context, but must be addressed by a
  general, explicit typed dependency handoff, not by abandoning validation.

**Priority 0 before declaring architecture fixed:** implement typed
per-candidate or source-clause handoff for lexically shared subject/date/
predicate/negation/correction without re-merging unrelated sibling
assertions into one Core natural-language request. Keep Core identity proof
and Writer safety unchanged. Explicitly assert exact actual downstream
model inputs for F06, F02, F23, and the other collapsed cases. Repeat the
27-case replays and only then carry out carefully capped real-provider
acceptance checks. The findings here do **not** authorize changing the
product flow or weakening provenance.

## Individual live observations

`completed` means the normal Core path returned completion and physically
marked notes were observed. It is not an independent proof of all
user-intended semantic details.

| ID | Live outcome | Local routed text count | Main observation / next investigation |
|---|---|---:|---|
| F01 | PARTIAL | 2 | First Temporal response incomplete/truncated; second independent route writes |
| F02 | FAILED | 1 | Temporal response incomplete/truncated with approximate time |
| F03 | NEEDS_ATTENTION | 1 | Core reference coverage refuses expanded/shared canonical-link graph |
| F04 | COMPLETED | 1 | Core wrote to one Day note; two candidates still combined in one original-text Core route |
| F05 | Compiler blocked | 0 | Unjustified inherited source predicate; safe rejection |
| F06 | NEEDS_ATTENTION | 1 | Generic two-fact input meets a narrowly specialized sequential-contact Core validator; rejection is not a Router parsing failure |
| F07 | NEEDS_ATTENTION | 1 | Core reference coverage refuses shared/expanded canonical links |
| F08 | FAILED | 1 | Temporal response incomplete/truncated |
| F10 | NEEDS_ATTENTION | 1 | Reviewer leaves relationship pending despite Planner producing a relationship plan |
| F11 | COMPLETED | 1 | Shared purchase transaction; Core wrote one Day note |
| F12 | FAILED | 1 | Core Planner chose ESCALATE; no write |
| F14 | PARTIAL | 2 | First conversation fact written; ambiguous `él` remains unbound, as required |
| F15 | FAILED | 1 | Temporal returned an exact day plus UNSPECIFIED for another ordering reference; route declined |
| F16 | NEEDS_ATTENTION | 1 | Core's source-to-fact lexical veto rejects one candidate |
| F17 | NEEDS_ATTENTION | 1 | Negated source; independent reviewer proposed facts, but sensitive-polarity coverage fails closed |
| F18 | NEEDS_ATTENTION | 1 | Mixed negated/affirmative source; sensitive-polarity coverage fails closed |
| F19 | FAILED | 1 | Temporal response incomplete/truncated for a self-correction |
| F20 | NEEDS_ATTENTION | 1 | Conditional alternatives; specialized semantic scope is not yet covered by Core |
| F21 | FAILED | 1 | Temporal response incomplete/truncated for compound dates and times |
| F22 | NEEDS_ATTENTION | 2 | Both dated task routes reached Core, but modality/task coverage did not authorize writing |
| F23 | COMPLETED | 1 | Two distinct Odyssey project-defect facts written; Temporal correctly skipped despite its name appearing as a component |
| F24 | NEEDS_ATTENTION | 1 | One of two source candidates remains pending in Core's independent review |
| F25 | NEEDS_ATTENTION | 1 | Property-subject evidence validator cannot prove each subject separately |
| F26 | NEEDS_ATTENTION | 2 | First Core route chose ESCALATE, dependent second route could not safely proceed |
| F27 | NEEDS_ATTENTION | 2 | First Core route chose ESCALATE, dependent ambiguous reference was not written |

## Priority by root cause, not phrase-specific patches

1. **Architecture first:** transfer source-role and Core-result dependencies
   as typed evidence while preserving separate executable fact units. Do not
   quietly restore a whole-message Core/Temporal prompt for convenience.
2. **Temporal output contract:** five responses (F01/F02/F08/F19/F21)
   reached provider status `incomplete` with truncated JSON. Review
   `max_output_tokens`, token reservation and a bounded explicit
   error/continuation policy, without hiding or retrying uncertain calls.
   Separately preserve approximate times and relative sequence scopes
   (F02/F15/F19) rather than coercing to exact time or blocking unrelated
   facts.
3. **Core candidate-to-fact coverage:** existing narrow two-person,
   sequential-contact, property, and N:M reference guards can reject
   legitimate broad semantic shapes (F03/F06/F07/F16/F25). These are
   genuine test-gate failures, not necessarily evidence of an unsafe model.
   Replace narrow assumptions only through generalized proof and negative
   regression tests, never suppress validation.
4. **Explicitly pending semantics:** pronouns with multiple antecedents
   (F14/F27), negation/polarity (F17/F18), conditionals (F20), and
   task modalities (F22). Safe decline is better than an unsupported write.
5. **Model-planner quality:** Core ESCALATE for F12/F26/F27 and reviewer
   non-matches F10/F24 need independent linguistic and schema review after
   the route-scope contract is corrected.

This report freezes the **observed** outcomes; it does not propose activation,
alter model versions, change personal canonical Notes, or turn unverified
semantic guesses into regression acceptance passes.
