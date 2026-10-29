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

### Third independent Generality review — SHA 3fc034f, FAIL (29 October)

An independent read-only Sol review of the 3fc034f SHA found **two new
repairable blockers**, neither covered by that SHA's passing 2,378 Python
and 259 JavaScript cross-surface gate:

1. The legacy Core reviewer could expand `source_quote` to the entire message
   although a planner fact's `source_evidence` described only one assertion.
   Checking relation membership against the **reviewer's broad quote** could
   therefore attach a verified partner to the separate children-only fact.
2. The Router rejected identical `self_relation_spans` despite a phrase
   occurring independently in multiple valid original-source assertions.

A subsequent unreviewed source patch narrows Core's relation authorization to
**each fact's original planner-anchored primary evidence**; an auxiliary or
broader quote is never another identity authority. The Router accepts repeated
verbatim group phrases only up to their actual occurrence count in the
unchanged original source, still capped at eight entries and independently
verified from fresh authenticated SELF facts. Negative broad-quote tests cover
both legacy and Core-anchored modes; a two-assertion real E3/Markdown/replay
fixture covers valid repeated phrasing. Neither workaround adds a phrase-based
rule, bypasses Core/E3 or enables unspecified ellipsis inference.

**Previous FAIL remains historical; this patch is not a new audit PASS.** The
reviewer also warned about the existing schema/prompt eight-group bound; no
model-facing prompt/schema has been changed after the authorized 12/12 GPT
calls. A new independent verdict on the patched SHA and a complete matching
source gate are still required; DEV app acceptance and durable actionable
clarification remain separate unresolved gates.

### Fourth independent Generality review — SHA 55a1372, FAIL (29 October)

The independent Sol source reviewer reproduced **two residual identity
provenance defects** after the first repair. A Planner fact could cite the
entire source as its *primary* evidence, subsuming a narrower independent
fact's person reference. And in the legacy mode, an explicit person's name
from a later assertion could be borrowed through the reviewer's broad quote.
Both were accepted by the previous validator despite a misleading fact link.
The same reviewer warned that the strict model prompt's unbounded wording
does not reflect the existing eight-group maximum, and that the executor's
scalar/list compatibility validation was looser than the stated prompt.
The FAIL is retained, not reclassified.

The next source-only repair makes Core compare original-source **primary
occurrence offsets for every atomic fact** when verified relationships are
involved. A relationship phrase or explicitly named person can authorize a
fact only when its occurrence lies in that fact's primary source anchor and
not in any *different overlapping fact's* primary anchor. Multiple distinct
relationship groups cannot be attached across two facts with identical broad
primary evidence. Shared or supporting context is never an implicit identity
handoff. This is a deliberately conservative abstention where source ownership
cannot be independently established; it may defer legitimate co-references
until a typed, reviewed fact-to-fact handoff exists. New adversarial cases
cover broad Planner and Reviewer citations in both modes, explicit names,
and equal overlapping anchors. The Router also requires its legacy scalar
to agree with exactly one list entry when present; scalar-only pre-Events
compatibility remains intact.

**No model prompt/schema or authorized provider budget was changed.** The
existing eight-group prompt mismatch is a known non-release warning; a
model-facing change needs a new authorized GPT gate. This patch needs an exact
SHA full regression, new independent audit, actual isolated app/browser E2E,
and pending-clarification durability before merge/deployment acceptance.

### Fifth independent Generality review — SHA db0793d, FAIL (29 October)

The new read-only Sol source review reproduced **two remaining source-bound
identity breaches** in both legacy and Core-anchored validator modes:

1. A broadly quoted first fact could inherit the later partner relation when
   the second fact's primary evidence contained only its verb, not the
   relationship phrase. Simply excluding *overlapping mention spans* did not
   exclude authority transferred through an overlapping atomic assertion.
2. Literal persons outside the verified SELF-member set could still be added
   to the wrong atomic fact using source-wide participants and quotes.

The subsequent candidate applies **conservative Core-only safety boundaries**:
any two *different overlapping* primary atomic evidence ranges with linked
people cause abstention, and every explicitly named person outside verified
SELF memberships must occur in that fact's primary source evidence, even when
there are no SELF relation groups, **or** be carried by the already-supported
`dependent_on_fact_index` from an earlier fact that itself has a proved
reference. This preserves previously verified declarative co-reference like
«Conocí a Maite; mañana tengo que llamarla», without borrowing unrelated
people or future assertions. The existing SELF-group membership checks
remain mandatory. New adversarial cases reproduce both failures in both
coverage modes. The trade-off is intentional: valid assertions with shared
context may be withheld pending a source-grounded, typed fact-person
attribution/handoff that is independently validated. A verb-only source
fragment is **not** evidence that an unrelated family member participated.

Historical FAILs remain immutable. This source safety patch is not a fresh
independent PASS, a semantic GPT-provider evaluation, or end-user app E2E.
A bounded next-generation fact-specific relationship/identity proof requires
model-facing contract evaluation before it can promise full automatic
co-reference resolution; do not silently loosen this validator or treat a
passing deterministic suite as that evidence. The known eight-group capacity
warning and the missing durable actionable pending clarification remain open.

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

## Actual isolated Chromium UI regression (29 October, source `4747a0f`)

A new **test-only** `issue157_day` scenario in the existing
`scripts/odyssey_browser_synthetic_p4.py` (paired with its `.cjs` driver)
uses a disposable `TemporaryDirectory` vault/actor and the actual branch
Odyssey HTML/JavaScript UI, Core/E3/Markdown, Notes API, source-bound family
proof and request replay. Recorded Router/Planner/review outputs replace
paid GPT, and a narrowly allowlisted HTTP adapter stands in for n8n.
It is NOT deployed DEV, real-model acceptance or public Cloudflare Access.

Actual Chromium was started on the Pi via the already vetted
`e6-chromium-runtime-deps` **process-local** library path. Both mobile
390×844 and desktop 1280×960 runs returned PASS: visible Chat typed/submitted
the accented synthetic memory; one `calendar_day` contained two physical
facts and three already-existing Person links; no Events/Tasks or duplicate
people were created. Browser confirmation, actual execution graph, Notes
readback and browser reload succeeded; same request ID replay left all
physical Markdown byte-for-byte unchanged. The browser graph correctly shows
**one Core write receipt** for a single note containing **two atomic facts**;
requiring two separate note/write receipts was an error in the old
single-case test harness, not a missing persisted fact.

Independent unchanged older `maya` and `e4_person_task` browser scenarios
were rerun and passed, including graph/reload, actual Person+Task E3 and
replay. All browser operations were confined to temporary synthetic data;
none targeted `/data/odyssey` or `/data/odyssey-dev`. This evidence does NOT
close the required **authenticated, isolated real n8n + real GPT** app path,
or the durable actionable pending clarification for unknown relationships.
See GitHub issue #158 for why a new Cloudflare token must NOT access the
shared DEV identity/vault before isolation is proven.

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
