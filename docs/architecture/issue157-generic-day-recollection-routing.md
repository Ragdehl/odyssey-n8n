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
- **Still required:** bounded, explicitly authorized fresh GPT evaluation
  of the new prompt/strict schema; no golden edits to mask failures. A passing
  fake model test only proves deterministic enforcement, not real model
  behavior. If misroutes remain, diagnose the model decision, temporal/date
  ownership and pending clarification separately before further changes.
- **Still required before DEV promotion:** authenticated browser → real n8n →
  real model → Core/E3 → synthetic Markdown → Notes/Day readback and
  replay on the exact release SHA. Do not mutate shared DEV/PROD personal
  vaults, merge a draft PR or enable flags without separate approval.

This note is an incremental, falsifiable hypothesis for #157, not proof
that the originally observed route was caused solely by scalar cardinality.
