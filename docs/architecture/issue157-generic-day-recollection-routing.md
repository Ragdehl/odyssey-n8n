# Issue #157 — generic past-day recollections and multiple SELF relation groups

**Status: source-only candidate, not a production model acceptance or DEV deployment.**
Base: merged `dev` after PR #156, 28 Oct 2026. Source issue:
[GitHub #157](https://github.com/Ragdehl/odyssey-n8n/issues/157).

## Observed boundary and non-goals

The private DEV report of 27 October was a completed family/day recollection
with several facts and existing SELF-linked family relationships. UI returned
generic clarification, reason `FULL_SOURCE_REVIEW_OR_IDENTITY_UNVERIFIED`,
zero writes; only the initial Events-enabled Router model span was observed.
**This does not prove the Router's exact output**, or that the later Core
identity resolver failed: no direct Core attempt was observed. The raw user
message remains private; all source fixtures in this PR are synthetic.

A source can contain several independent verified relationship references
(e.g. the narrator's children AND partner), while the currently active
Events-enabled Router had only one `self_relation_span`. A single cardinality
cannot attest both sets of already-canonical members. This PR adds a bounded
array of **exact copied source spans** to the Events-enabled route, without
changing the frozen legacy Router contract. The list is only a suggestion:
Core must independently re-ground **all** groups against fresh authenticated
SELF-owned Markdown, deduplicate by canonical ID, detect conflicting names
and recheck the relationships before and during writes. If different
relationship phrases come from the **same indivisible canonical atomic
fact**, its combined link set cannot prove each separate membership,
so Core must abstain instead of cross-attributing people. Missing, stale,
duplicated, excessive or unverified sources abstain before mutation.

The first **six** authorized live GPT-6 Luna low-effort schema-bound
Router checks found 4/6 strict PASS: all six correctly chose Core rather
than Events, but the Spanish two-group source collapsed two coordinated
relationship references into a single combined span, and the French
two-group source omitted the singular partner reference. English correctly
returned both, and single/no-group controls passed. No private notes or
real user data were sent; signed private receipt is outside Git in
`.odyssey-agent-runs/issue157-live-20261028/attempt-ledger.json`.
The contract now requests minimal distinct references (singular or plural),
each verbatim and in source order. The next fresh gate must not relabel those
two failed outcomes as successes.

### Actual bounded fresh provider evaluation — completed

The user explicitly authorized **up to 12 real paid GPT calls**. The
Raspberry executed **exactly 12** against the actual Events-enabled strict
JSON contract, GPT-6 Luna, low effort, with no SDK retries and 1,700
max-output tokens per call. All inputs were synthetic; the protected
EnvironmentFile was loaded by two transient systemd user units, whose
sandbox hid DEV and PROD directories. Signed reservation receipts in
`.odyssey-agent-runs/issue157-live-20261028/` remain private and are
separately anchored to source/prompt/schema SHA-256 fingerprints.

| Prompt/source | Calls | Required primary route and exact relation spans |
| --- | ---: | ---: |
| Initial PR #161 `b48c179`, prompt `cd0eb5f67a9f` | 6 | **4/6** |
| Corrected `fb137fa`, prompt `88bc44e513d2` | 6 | **6/6** |
| Entire authorized campaign, never resetting prior failures | **12/12** | **10/12** |

The two initial failures were **Spanish coordinated relations merged into
one span** and **French singular partner missing**. The corrected prompt
then passed both exact multi-relation cases plus one unknown-destination
recollection, a future scheduled Event, an Event reschedule and a real Task
obligation. Total measured SDK usage: 16,710 input and 2,793 output tokens;
no exact billing cost inferred. **No additional GPT calls are authorized.**

**Scope caveat:** One corrected unknown-destination route returned a lone
Core `app_scope` with `depends_on_another_scope=true` while describing
Temporal as its dependency. This is inconsistent as an independent
*user operation* scope; the current Core-only executor ignores that
non-authoritative app_scopes hint and still performs independent
whole-source coverage before writing. The **6/6 score is strictly for the
predeclared primary capability and exact relation-span checks**, not full
semantic endorsement of every optional model field. Keep this warning
visible for independent reviewers; do not rewrite expected results.

### Independent read-only code quality review and first repair

An actual independent GPT-6 Sol / medium read-only source reviewer assessed
the source-only PR SHA `e4a76f7` and returned **FAIL** with one repairable
blocking finding (private raw review retained; it has **not** been rewritten).
With the expanded Events-enabled Router, a legitimate upcoming Event
mentioning a canonical singular SELF relationship could be proposed with
a `self_relation_spans` entry, while the Events branch rejected every
nonempty list before Core grounded the relationship.

The next change moves the **existing canonical SELF relationship proofs
before Events delegation**, rechecks all of them at the delegate boundary,
and rejects unverified/stale groups. A valid future appointment with a
proved partner now reaches Events; one with a missing canonical partner
is safely withheld. The mixed Event+Task partition remains conservative.
The Event delegate remains responsible for its own independently reviewed
lifecycle, actor authorization and E3 semantics; the Router still cannot
declare an Event write. New isolated positive and negative regressions
exercise this distinction. The older independent FAIL stands until a new
independent reviewer examines the repair's actual SHA.

### New independent Generality review (29 October, source SHA 75632c1)

An additional *independent* GPT-6 Sol / medium read-only Generality reviewer
returned **FAIL**, recording two blocking cross-domain gaps and one warning.
This verdict remains immutable in private
`.odyssey-agent-runs/issue157-live-20261028/review-generality-sha756.json`:

1. The independent **Event + Task** path still rejected every nonempty
   relationship span despite real valid future appointments with a partner.
   Source partitions must independently attest exact source bytes and retain
   previously grounded SELF relationships rather than silently deleting them.
2. Previously, verified members from all SELF groups were passed to the
   whole-source coverage checker as a single unscoped list. That verified
   each *person*, but not that the person participated in the *particular
   atomic fact*. Distinct source assertions could cross-attribute groups.
3. Warning: router instructions said "any number" while the executor
   conservatively limits source relation spans to **eight**. This is a
   documented finite safety cap, not permission to drop the ninth member.

The new source candidate introduces an **optional original-source group
provenance map** to the existing Core coverage validator. A person verified
by a SELF group must belong to a relationship phrase literally supporting
the specific atomic fact. Independent facts with distinct groups cannot
borrow one another's members. Explicit literal source name evidence remains
a separate checked source. A later elliptical source statement can still be
recorded **literally** in the canonical Day, but no individual identity link
may be inferred from earlier collective membership without an additional
reviewable source-bound cross-fact semantic proof.

### Second independent Generality review — source SHA 0547e62

A fresh Sol read-only review returned **FAIL** despite the successful
source-only mixed Event+Task repair. It independently reproduced two unsafe
or incomplete edge cases in the old *implicit ellipsis inheritance* clause:

- The source "Mis hijos y mi pareja salieron. Ella cocinó." could give
  every known group member a link in the second, singular fact.
- The source "Mis hijos jugaron. Después descansaron. Mi pareja cocinó."
  could refuse a continuation belonging only to the earlier children,
  because the later unrelated partner group was also mentioned.

The revision removes automatic cross-sentence group inference, rather than
hardcoding singular/plural grammar for individual languages. The confirmed
first fact retains its exact canonical Person links; a second elliptical
fact remains durable literal Day content, **without unproven individual
links**. The negative source now fails safely, and legitimate continuations
with ambiguous membership are recorded without an invented relationship.
A later full-featured solution requires a separately reviewed, typed
fact-to-fact membership handoff with independent source evidence and model
testing. This source-only partial safeguard must not be marketed as complete
automatic attribution of every unnamed participant in all continuations.

The prior Generality FAIL on `0547e62` is retained; this revision is not
a retroactive PASS or an authenticated browser release gate. Private JSON:
`.odyssey-agent-runs/issue157-live-20261028/review-generality-sha054.json`.

The Event+Task independent partition now permits already verified SELF
spans, requires each span to map to **exactly one** byte-exact reviewed
scope and rechecks the original actor-owned canonical SELF proof **after
both operation preparations and immediately before the first E3 write**.
A later E3 operation may invalidate the derived verified catalog; reentering
that stale cache between two independently planned operations could reject
the second operation after the first was already written. The request-level
operation manifest and each delegate's E3 guard still own their respective
writes; we do not bypass the catalogue or silently re-index the entire
vault in the critical path. Tests cover positive future Event + independent
Task with a verified partner, unverified partner, SELF source changed during
preparation, E3/Markdown readback and replay.

These are **repairs in progress**, not new Generality PASS. They must be
subjected to the full offline gate, then a fresh independent review on the
final commit and product-authenticated synthetic browser E2E. Any source
change after the 12 authorized product GPT calls is **Core-side
validation/delegation only**, not a revalidated new Router prompt.

A genuine GPT Router response from the corrected Spanish multi-relation
case has been frozen in
`tests/fixtures/issue157_recorded_live_router_v2.json`. Its
`test_saved_real_gpt_router_v2_does_real_core_e3_day_and_family_readback`
fixture is a genuine **Router replay + fake downstream model review +
real Core/E3/physical Markdown** test with two facts, existing family
links and idempotence. It is **not** a fresh complete-model public browser
test and must not be described as one.

The Event-capable Router prompt is also clarified at the **general intent
boundary**: a completed dated recollection is durable Core/day knowledge;
a schedule, future occurrence or Event lifecycle command remains Events.
Two assertions of one past-day recollection do not create two future Events.
The Router does not invent note IDs, persons, destinations or date precision,
and no string-matching override in the local executor is permitted.

Out of scope: changing actual DEV family notes, replaying the private
utterance, new standalone Journal writer, new note schema, unilateral
Calendar Events from past tense, extra agents/services, or any production
provider budget expansion. Existing `calendar_day`, source coverage,
Temporal, Core/E3 and Git/readback remain canonical.

## Bounded model evaluation matrix (must be run on production GPT before enabling)

Each model test must inspect the **actual strict JSON schema** and record the
routing decision/coverage on the full original source. Use fresh synthetic
notes, authenticated fake SELF and fixed local clock; no use of private source.

| Class | Synthetic input / shape | Required behavior |
| --- | --- | --- |
| Same-day shared memory | Completed plural family visit to two independent places, 2 relation groups | Core + Temporal, two facts, all existing people |
| Single relation | Completed family outing, one existing group | Core + Temporal, one relation proof |
| No relation | Completed trip with no family references | Core + Temporal, zero relation spans |
| Several unrelated facts | Three separate same-day statements with shared date | N Core facts, no silent drop |
| Unknown relation | Completed group visit, no canonical SELF fact | Fail closed; pending actionable clarification preserving original |
| Explicit future appointment | Scheduled museum visit next week | Events + Temporal; do not rewrite as completed Day fact |
| Event lifecycle edit | Reschedule a future excursion | Events, no unintended Core fact |
| Actual obligation | Bring tickets tomorrow | Tasks + Temporal |
| Negative/uncertain memory | Denial, hypothetical or uncertain visit | No affirmed past fact |
| Different languages | Spanish, French, English narration of completed day | Same general route, no phrase whitelist |
| Unknown destination | Unresolvable place reference but known family | Preserve proven day information, clarify only unknown place |
| Replayed request | Same authenticated delivery ID | Exactly zero additional physical writes |
| Cross-user evidence | Relation group belongs to another SELF | No identity reuse or writes |

## Verification and release gates

- Deterministic synthetic Core/E3 test: two original facts on one Day,
  all verified family names linked, one consistent Day, no duplicate on
  same request replay, no Event delegate.
- Contract compatibility: frozen non-Events Router remains unchanged; new
  Events route requires typed bounded `self_relation_spans`, and old
  scalar responses remain conservatively readable during migration.
- Negative cases: missing relation, altered/late SELF evidence, duplicate,
  over-capacity, stale member evidence, model hiding attested members,
  inappropriate Events route, no invented participants.
- Full offline Python, JS and workflow contract gate + independent reviewers.
- **Completed:** a budget-bounded fresh GPT Router evaluation, with exact
  12/12 budget and separate first/second prompt versions above. The
  optional app-scope inconsistency must be reviewed independently; do not
  conflate this with end-to-end integration.
- **Still required before DEV promotion:** authenticated browser → real n8n →
  real model → Core/E3 → synthetic Markdown → Notes/Day readback and
  replay on the exact release SHA. Do not mutate shared DEV/PROD personal
  vaults, merge a draft PR or enable flags without separate approval.

This note is an incremental, falsifiable hypothesis for #157, not proof
that the originally observed route was caused solely by scalar cardinality.
