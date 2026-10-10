# Router fact-candidate units v1 — design contract (not active)

Status: **BLOCK 1 / PROPOSED SEMANTIC CONTRACT — awaiting human design review.** Block 2 checkpoint storage remains optional and inactive. Block 3 has a frontend-only diagnostic preparation: it can render already-validated v1 route evidence, an explicitly supplied source-free checkpoint snapshot, and a local test-only candidate preview. It adds no prompt, runtime, note schema, provider call, n8n/browser transport, deployment, or canonical data change. Historical Router v0 behavior and its frozen evidence are unchanged.

## User outcome and objective

A compound user message should be split into the smallest **independently manageable semantic assertions/actions** rather than just self-contained text spans. Correcting, removing, or deferring one should not accidentally affect other facts that share its date, participants, verb, polarity, or other context. Preserve exact source provenance, avoid invented identities and chronology, and keep specialized apps narrow and Core authoritative for knowledge semantics and mutation.

**Terminology:** `fact candidate` / semantic unit denotes a proposed independently manageable proposition, activity, plan, conditional, or task intent in the user's wording. It does **not** assert that an event occurred, authorize a persisted atomic fact, create a Note, select an app operation, or correspond one-to-one to a `KnowledgeUnit`, `WriteAction`, Note, or historical `fact_locator`. Core can accept, clarify, reject, or legitimately represent multiple candidates through one canonical operation. A group event may remain one shared relational statement with many participants.

## Architecture challenge — RECONSIDER the direct one-route-per-fact shortcut

**Material concern:** Router v0 requires a non-overlapping exact partition of the user's text (`validate_route_plan`), and dependent route metadata accepts only one source-visible referring expression paired with a Core-verified canonical identity. It cannot represent two facts sharing the **same** original predicate (`Marta y Luis viven en Lyon`), two products sharing one transaction, omitted `iremos` in a successor, or a common date applying both backwards and forwards. Pretending that two stand-alone rewritten texts were exact routed spans breaks provenance. Reusing the current `depends_on` mechanism for source-level temporal/grammatical inheritance would incorrectly make the second fact depend on successful persistence of the first.

**Simpler alternative:** One initial Router call yields **candidate semantic units with validated source anchors and typed source-context dependencies**, then groups/dispatches by appropriate capability. Source context is resolved/validated as read-only interpretation for the **whole request** before canonical writes. Maintain a separate path for actual Core-proven identity handoffs. Continue to use existing Runtime coordination, Temporal interpreter, Core planner, Markdown vault, and request-detail diagnostics. Do not build a second planner, event store, entity resolver, tracing service, or app-specific writer in Router. Reuse the existing `RoutePlan`/execution path where possible, with an explicit versioned adapter for the new semantics rather than mutating frozen v0 evidence.

**Trade-offs:** More structured output, validation, source-anchoring complexity, and potentially more Core plans/routes or diagnostic entries. Gains include lossless context across independent units, easier correction and failure diagnosis, and simpler per-unit interpretation. One LLM call for initial segmentation is the target; any cost/latency benefit must be measured, not assumed.

**Recommendation:** PROCEED with this **design-only** block. New runtime schema, write policy, and diagnostic durability need subsequent approval and separate tests/live Luna gate. `Human decision required: YES` for the remaining open product/diagnostic decisions at the end of this document.

## Canonical responsibility boundary

```text
Original immutable user message
    -> Router: candidate units, source anchors, typed contextual edges, capability hint
    -> Local validator: source coverage, reference scope, typing, ambiguity, no invented content
    -> Temporal: interpret dates/times on grounded inherited+local source expressions
    -> Core: semantic owner, identity verification, plan/fact count, preflight, write
    -> existing request-detail projection: inspected validated evidence + actual outcomes
```

- A candidate unit is a proposition or action that could be corrected/deleted on its own *without changing the truth of another*. One mutual encounter (`Marta y Luis se conocieron`) is one relational unit; two residences (`Marta y Luis viven en Lyon`) are two property assertions; pan and milk are two item-level assertions **of the same purchase**, not two independent shopping trips.
- **Subject and participants are semantic roles, never fixed entity types.** A subject may refer to an appliance, house, vehicle, document, project, city, task, person, group, an otherwise unknown entity, or a literal without a canonical Note. A participant/object/location can likewise refer to any Core-recognized type. Router does **not** emit NoteSchema types (`Person`, `Project`, etc.), decide whether to create a Note, or assume that a grammatical subject is the final canonical knowledge owner. Core validates note type, identity, linking, group/literal policy and final semantic ownership against the schema and source. The source-bound role labels `subject`, `participants`, `object`, etc. are generic and remain independent of ontology. A clause's actor may change while a previous entity becomes its object (e.g. `El informe llegó ayer y hoy lo envié a Ana`).
- Shared context is typed by role: `participants`, `subject`, `predicate`, `object`, `date`, `time`, `location`, `polarity`, `condition`, `modality`, `ordering`, or `transaction`. A link can cite source **before or after** its unit, and links may apply only to some roles. A new explicitly scoped value overrides an inherited value of that role without stripping other roles. Do not infer that `después` means an exact clock time; `sobre las 16h` is approximate, not an exact 16:00 instant.
- Scope must be semantically grounded, not mechanically propagated to every following clause. For example, `Ana compró pan y Luis también` changes the actor; `no vi a Ana, pero sí hablé con Luis` does not propagate negation. A singular/plural verb is evidence but not proof of a particular canonical participant list. An uncertain referent is visibly unresolved, never silently bound.
- Router records **references to existing original source**, not duplicated/reconstructed source sentences, computed ISO dates, person UUIDs, Note targets, property writes, or Markdown. A unit can reference the same token spans as another unit. Preserve unselected/overridden/corrected source as provenance, even if it yields no active fact candidate. Exact source coverage must still be locally checked; the old disjoint partition alone is no longer the appropriate unit-level invariant.
- Referential identity is **not** the same as source continuity: the already implemented `él -> Eric` handoff uses authoritative post-write Core evidence and a write preflight guard. Source-level `mañana`, `iremos`, or participant-set scopes should not need a predecessor's canonical write to succeed. Their validated interpretations must be available for preflight *before* mutation. Neither route metadata nor the diagnostic graph grants identity or mutation authority.
- Calendar remains read/presentation; Temporal handles date normalization; Tasks owns its lifecycle semantics when enabled; Core handles generic fact/identity/note/write logic. A candidate may lead to `CLARIFY`/`NEEDS_CAPABILITY` rather than a semantic write. Avoid creating new `calendar_day` ownership inside Router.

## Non-executable fixture and acceptance oracles

The 22 **human-agreed design examples**, plus four additional generic-subject regression examples (F23-F26, proposed for review), live in [`../../benchmarks/application_router/fact_units_v1.design.json`](../../benchmarks/application_router/fact_units_v1.design.json). They are **future expected semantic decompositions**, not predictions of current Router v0 or passing production model tests. Each case defines the source, expected number and meaning of candidate units, context edges, and a safety caveat. Do **not** weaken historical frozen Router v0 regressions to match this unimplemented v1 direction. When implementing, version and test a new model contract, replay the 22 examples with a production-equivalent Luna/low live gate, and add permutations/adversarial probes without overfitting to literal phrases.

| ID | Core challenge | Expected candidates | Distinction that must survive |
| --- | --- | ---: | --- |
| F01 | yesterday park/cinema; today concert | 3 | participants persist, date changes, cinema not exactly 15:00 |
| F02 | afternoon snack, tomorrow park, Sunday market | 3 | `esta tarde + sobre 16h` one approximate event |
| F03 | tomorrow park then cinema | 2 | date/group inheritance and non-exact order |
| F04 | same date, two times | 2 | date inherited but 12:00 != 18:00 |
| F05 | dinner on Friday and Saturday | 2 | shared predicate; different people/place/date/time |
| F06 | saw Ana and bought bread | 2 | date shared; Ana not bread-purchase participant |
| F07 | Bea at 15, Luis at 17 | 2 | same day and predicate; distinct time/object |
| F08 | two doctors at the same hour | 2 | different subjects/destinations, shared hour |
| F09 | Marta and Luis live in Lyon | 2 | shared predicate, independently true properties |
| F10 | Marta and Luis met in Lyon | 1 | single joint relationship, no duplicate encounter |
| F11 | bought bread and milk | 2 | item facts, **one** purchase transaction |
| F12 | same group cleans then assembles | 2 | activity order and group continuity |
| F13 | Eric then `él`, unrelated bread | 3 | explicit pronoun needs guarded Core binding |
| F14 | Eric and Luis, then ambiguous `él` | 3 | identity ambiguity is not permission to guess |
| F15 | children, Bea, self actions | 3 | date retained, subjects changed |
| F16 | Ana purchased and Luis `también` | 2 | shared predicate/object, subject replaced |
| F17 | did not see either Ana or Luis | 2 | negative polarity on both propositions |
| F18 | did not see Ana; did talk to Luis | 2 | polarity scope not copied into positive clause |
| F19 | park plan corrected to cinema | 1 | earlier plan superseded, not saved as another plan |
| F20 | weather-dependent alternatives | 2 | conditional branches, not two confirmed events |
| F21 | Monday and Wednesday recurring class | 2 | same later-mentioned time scoped backwards |
| F22 | call Ana, write Luis, prepare invoice | 3 | task ownership, shared/changed dates |
| F23 | Project Odyssey has Router/Temporal bugs | 2 | one non-person subject, independently manageable problems |
| F24 | vehicle in repair shop and passing inspection | 2 | same vehicle subject, date only on second claim |
| F25 | house has damp and needs a roof repair | 2 | house subject, interior location not another subject |
| F26 | report arrived yesterday and I sent it today | 2 | report changes from subject to object; speaker becomes actor |

### Design proof obligations for implementation

1. Exactly the expected atomic candidate count and role separation for every accepted fixture; no missing negation, condition, cancellation, object, relationship or chronology. A semantic unit may have multiple original span anchors; no fabricated source words.
2. All context edges must point to exact source-grounded evidence with an explicit role and scope. Validate source-text correspondence/occurrence, avoid ambiguous repeated occurrences, cycles and ungrounded dependencies. A forward source-scope reference is not the same as a forward canonical-write dependency.
3. Same shared source evidence may be consumed by multiple units while each unit has a distinct request-local candidate ID. Nothing in v1 yet changes durable Core fact identity or note schema. Locators are allocated only for **persisted** facts by Core.
4. Resolve all applicable temporal and source-scope consistency preflight before irreversible Core writes; preserve `unspecified`, `approximate`, `unknown`, and `failed` distinctions and the original wording.
5. Preserve the existing Core-proof-only **type-agnostic** identity model, stale guard and fail-closed behavior; surface unknown source-identity choices as unresolved. Router never binds a unique canonical Note ID or guesses its NoteSchema type, whether the subject is a person, object, location, project, task, or literal.
6. A candidate's source-to-Core journey must be separately observable, including split/attach, scope inheritance, Temporal normalized evidence, Core plan, validated entity binding, and actual mutation outcome; do not label proposed context as Core-verified context. Old request-detail shape must remain displayable.
7. Verify bounded production Structured Outputs, cost/tokens, performance with 1/3/8/12+ units, existing v0 cases, synthetic adversaries, and vertical provider-free Router -> Temporal -> Core -> disposable Markdown and replay; protected model prompt/schema changes require a separately reviewed Luna/low live gate.
8. Multiple candidates in a single request must retain existing request-level deduplication, per-fact correction/removal support, and safe status reporting. Do not claim transaction-level atomicity unless implemented and proved.

## Planned work / exclusions

Block 1: this accepted-design record plus reviewed open decisions and non-executable oracle. **No functional behavior changes.**

Block 2: extend existing actor-local `request_detail` and checkpoint semantics only after reviewing durable privacy/size/retention/error conditions. Current detail has a 64 KiB limit, flow max 8 routes and per-route max 16 stages; an overflow must never suppress an acknowledged successful canonical write. No raw model JSON, hidden reasoning, secret, note-content copy, or new tracing database.

**Block 2 preparation (not deployed):** an opt-in, actor-root-bound checkpoint seam retains up to 64 validated runtime milestones per request (rolling sequence with an explicit truncation marker) and the latest checkpoint: request ID, whitelisted stage, enum outcome (`milestone_observed`, `result_persisted`, `processing_returned`, or `failed_or_unknown`), monotonic sequence, and timestamp. It uses the existing progress signal rather than new execution instrumentation; it is non-authoritative, cannot retry or write, and does not replace authoritative delivery replay. Each atomically replaced record holds a bounded source-free sequence and its latest stage. Records reject corrupt/invalid input, mark truncated histories honestly, and apply only the approved checkpoint retention/capacity policy. Optional diagnostic failures are swallowed so they cannot interrupt canonical writes. Default runtime composition does not enable the seam or choose retention/cleanup.

**Approved retention implementation (feature branch; DEV activation remains later):** retain source-free checkpoint histories for at most **30 days**, with a **maximum of 500 request records per actor-local diagnostic root** (the existing 64 milestone/16 KiB per-record budgets remain). The feature branch prunes only validated diagnostic checkpoint files, oldest eligible first, atomically and strictly inside the already selected actor-local diagnostic root. At capacity it prefers evicting old terminal successful/returned histories before recent failed-or-unknown/incomplete cases. A full/unavailable diagnostic store must not stop conversation delivery or canonical writes. Never delete `request_detail`, canonical notes, pending clarifications, delivery-idempotency evidence, user knowledge, or any shared/production directory through this retention mechanism. Treat incomplete checkpoints as **outcome unknown**, not automatically failed or successful; require authoritative delivery replay for confirmation. No hidden retry. Expired or unavailable histories remain honestly absent; last-stage evidence is not write proof. Default runtime checkpointing remains opt-in: this change adds no DEV wiring, web API, cron/daemon, tracing service, or new security boundary.

**Still open:** recovery visibility and production capacity/activation remain future decisions. A later read-only graph may consume these bounded checkpoints together with final assistant-turn `request_detail`, but must show an interrupted/failed checkpoint as unknown rather than completed and must never infer a write from it.

Block 3: graph shows route-by-route observed stage I/O, Core-verified entity evidence, temporal evidence, route status, and actual validated write outcomes without treating a completed route as proof of a note write. It retains legacy fallback and mobile horizontal route navigation. The prepared checkpoint renderer accepts only the existing bounded, source-free checkpoint record and explicitly says delivery/processing milestones do not confirm a note. A separate local test-only candidate preview validates candidate IDs, exact message-grounded spans, generic roles, provenance, and proposed candidate dependencies; it is visibly design-only and is not part of `request_detail`, n8n, browser transport, or persistence. `verified` in that preview requires the supplied test projection to carry `authority: "core"`, but remains a display label rather than new authority. No candidate semantics are activated until Block 4's reviewed adapter and allowlist work.

Block 4: implement + version the candidate segmentation/dispatch with a contract adapter; keep protected v0/Temporal/Core guards and test rollback in isolated DEV. No production or real-vault deployment until separate authorization.

**Block 4A implementation checkpoint (isolated feature branch; NOT active):**
`odyssey_apps/fact_candidates.py` now offers a closed version-1 candidate proposal
schema, local validation of exact original Unicode substrings with zero-based
occurrence discriminators, locally calculated character offsets, request-local
candidate IDs, generic source roles and earlier-unit source-context inheritance.
It also exposes a single-call **injected-provider adapter** with `store=false`,
a bounded input/output contract and no credentials, resolver, persistence, or
execution method. It is **not connected to runtime routing**: the existing Router
v0 schema, prompt, Core/Temporal route contract, model behavior and canonical
Markdown remain unchanged. The 26 historical *design* examples (56 candidates)
validate structurally through this implementation with no provider calls. These
checks prove source correspondence and field safety, **not** that Luna actually
recognizes the right 56 semantic units. Adversarial local checks reject invented
source, invalid Unicode occurrences, extra canonical/write fields, unsupported
roles and incorrect source-context predecessors. An optional local-only preview
projection has passed the existing browser validator for 26/26 examples with 56
cards; inherited labels cite the actual earlier role source when it exists and
never claim Core `verified` evidence. No new product request-detail data crosses
n8n/browser allowlists.

The initial representation uses the source literal plus occurrence discriminator;
providers never supply trusted character offsets. Later-occurring dates/times can
be scoped to earlier candidate units without a write dependency. All accepted
candidate anchors and scopes are checked against the original source, which is
retained in full even when a correction supersedes a proposed fact. The validator
**cannot prove grammatical correctness**, unique real-world identity or whether
all source assertions were split: those require frozen model oracles and Core
preflight. The current same-role preview intentionally omits evidence it cannot
ground rather than making up inherited wording.

**Block 4B1 source-scope/Temporal bridge (same isolated branch, read-only):**
`odyssey_apps/fact_temporal.py` joins a validated original-message
`FactCandidateProposal` to an independently validated `TemporalInterpretation`
from that **same immutable full source**. It checks exact original mention
positions and preserves per-unit explicit and earlier-inherited source roles;
new explicit date/time wording overrides the inherited role while leaving
other roles untouched. A shared later time may refer to two earlier semantic
candidates without moving text or requiring either write to succeed. The
bridge distinguishes matched, unsupported/unspecified and missing Temporal
results; it does not promote approximate `sobre ...`, `time_relation` or date
range evidence into an exact Core instant. The returned evidence is provisional
and is **not** inserted into `DomainInterpretation` or any Core write. Tests
cover F01/F02/F08/F21/F26, overridden dates, absent Temporal, and source
mismatch, with only injected synthetic Temporal interpretations and no API.
The existing Temporal interpreter and its model-facing contract are unchanged.

**Block 4B2 (isolated read-only Core planner seam; no runtime activation):**
`odyssey_core/candidate_context.py` now independently validates a sealed,
request-local version-1 `CoreCandidateContext` built by the narrow
`odyssey_apps/fact_candidate_core.py` projection. It verifies exact original
source character offsets again at the Core boundary, acyclic inherited
source-role references, kind/state/role allowlists, 26-candidate/16-role and
16 KiB context bounds, and forbids Note type, UUID, mutation intent and
persistence instructions in the packet. The *existing* `OpenAILunaExperimentalPlanner`
accepts it solely through a new **optional** `candidate_context` parameter;
request mismatch fails before provider I/O, and the evidence is appended only
**after** the established Luna dynamic-context/cache breakpoint with explicit
"unverified" instructions. With no candidate context, the production Luna
prompt and strict result JSON schema remain **byte-for-byte unchanged** from
checked-out DEV `6ae8695` (tested SHA-256 for fixed context, including static
prefix). No normal composition path supplies the argument; it is inactive in
DEV and production, and Sol, Temporal, Router v0 and existing Core execution
are untouched. Candidate context is not `DomainInterpretation`: exact normalized
date/time authority still flows exclusively through the existing Temporal
`DomainInterpretation`, not through lexical source edges.

One provider-free vertical test injects fixed Router v1, existing Temporal and
real Luna planner Responses results for F13 and confirms three source candidates,
three independent Temporal readings, full original user request, and a safe
Core escalation result with **zero writes**. F14 checks that the ambiguous
pronoun remains unverified. Together with 26 Core-side design-fixture checks,
these are contract/injection tests, **not real model semantic proof, validated
per-candidate write correlation, or runtime persistence tests**. The new opt-in
Luna prompt is model-facing and must undergo its own narrowly scoped frozen
GPT-5.6 Luna/low live gate (Router's new GPT-6 Luna/low prompt needs a separate
gate) before any active deployment. A failing/blocked provider gate must not
be bypassed or described as an acceptance pass.

**Block 4B3 disposable real-Core-write experiments (isolated; NOT activated):**
`tests/runtime/test_fact_candidate_writes_e2e.py` now passes manually frozen,
Core-compatible `RequestPlan`s to the **actual** `execute_request` / canonical
`VaultRepository` writing pipeline, but *only* under pytest's disposable
`tmp_path` Markdown vault with synthetic data, inert retrieval/context
providers and no OpenAI calls. It verifies F01's three activities produce
three persisted facts across two Day notes (without copying the first clock
time to the other day), F11's bread and milk remain two item facts in **one**
Day note rather than duplicated purchases/notes, same-request replay does not
duplicate their facts, and F14's two resolved source clauses may be written
without turning the ambiguous final `él` into a canonical link. These are
**hand-authored Core plan** scenarios; they do not prove Luna produced such
plans or that group links/semantic ownership are accepted in production.

The adjacent `odyssey_core/candidate_write_observation.py` creates a bounded,
read-only receipt from **actual Core** `ActionResult`/`UnitResult` statuses and
Core's real write fact ordinals, rejecting mismatched action indices, duplicate
unit outcomes and a different original user source. It intentionally marks
**every** source candidate `unattributed`: neither candidate ordering nor
Core unit/fact counts prove a source candidate was durably persisted. In F14,
although the old Core engine reports `completed` for a manually selected safe
subset, the diagnostic still exposes `candidate-3` as ambiguous and does NOT
assert that the full message was handled. This is evidence of a **real remaining
safety/product gap**: before Router v1 is activated, a Core-owned, verified
candidate→plan/fact attribution and pending-clarification mechanism must ensure
independent validated writes can complete while unresolved/dependent candidates
remain correctly reported as pending, with idempotence/replay and source
coverage. Do not silently infer those associations or claim request completion
from a subset. This observational seam must not become a new write authority,
source-of-truth database, or product-visible verified graph before that proof.

**Block 4B4 Core physical readback (isolated; NOT activated):**
`odyssey_core/candidate_fact_readback.py` adds an optional, bounded read-only
check of **actual canonical Markdown** after existing Core execution. For up to
128 planned write facts and a bounded 5,000-note scan, it requires that one
valid Note with the exact successful Core unit's stable ID contains a *unique*
`odyssey:fact` marker with the same actual `ApplicationResult.request_id`,
Core-computed fact ordinal and exactly normalized Core plan fact text.
Successful plan/unit status alone never proves physical persistence. For a
replayed identical logical request, the same stable marker is accepted; when
a second request's identical fact text is silently deduplicated by Core,
that other request has **no matching marker**, so it is correctly **not
verified**. Corrupt markers, duplicate canonical Note IDs and incorrect action
receipts also fail closed. Tests cover three facts on two Calendar Day notes,
a two-item shared transaction, replay, cross-request deduplication, stale
source, copied canonical Note IDs and the ambiguous `él` withheld from writes.

Crucially this is **Core fact existence proof, NOT Router candidate semantic
attribution**. The readback contract explicitly returns
`candidate_coverage="unverified"` and
`safe_to_report_all_candidates_complete=false` even when every persisted Core
fact is proven. It separately exposes a source-candidate progress ledger: `unproven` for
every ordinary candidate and `ambiguous_identity` for unresolved pronouns;
neither is ever auto-promoted by physical Core markers. It also exposes the
original Core request status, including the known problem where a manually reduced
Core plan returns `completed` while an unrelated user clause remains pending.
Only a separately reviewed Core-owned mapping, validated complete source
coverage and existing pending-work/clarification machinery can resolve that
contract. No frontend, runtime, NoteSchema, marker metadata, cache or active
model prompt changed in this block.

**Block 4B5 (Core coverage preflight, isolated and opt-in):**
`odyssey_core/candidate_coverage.py` now requires an **explicit reviewed claim
for every candidate** in the original message and every planned atomic fact
ordinal, bound to the unchanged original message and exact Core `RequestPlan`
through source/plan digests. One Core plan unit can cover multiple source items
using distinct fact ordinals (F11), and independent facts can use different
Day notes (F01). Invalid or missing claims, duplicate attribution, invented
ordinals, stale plan/source and misleading non-pending ambiguous pronouns are
rejected. This first pilot supports only simple `record` facts with no Core
references, properties, deletions, migrations, negations, or conditional/
replacement scope; unsupported semantics must be deferred for review rather
than silently written. These checks are **structural**: an F11 pan/leche claim swap previously passed the structural check; the
subsequent conservative lexical veto now **rejects that mismatch before any
write**, without claiming that matches which pass are semantically verified. The mapping is not auto-generated from source order, text overlap
or fact counts, and existing Luna's output schema does not yet produce it.

`execute_request()` has a new **default-disabled** pair of Core-only arguments,
`candidate_context` and `candidate_coverage_factory`. If both are supplied,
it calls the explicit review factory **after Core planning and before any
write**, then revalidates the manifest with Core. A missing, forged, crashing,
misaligned or incomplete review returns `NEEDS_ATTENTION` with no actions or
vault mutation and the bounded clarification code
`CANDIDATE_COVERAGE_REVIEW_REQUIRED`. If independent writes do succeed but
some source candidates are explicitly pending, the opt-in result is `PARTIAL`
with `CANDIDATE_COVERAGE_PENDING`; the candidate-aware pending-work recorder
**does not exist** yet, so `pending_work.required=true`,
`persisted=false` and a clear bounded continuation-unavailable status are
returned. The existing plan-only pending recorder is intentionally *not*
misused to store a partial source-candidate state that it cannot resume. The
normal Core path remains unchanged without the new arguments. None of this
is active in Runtime/DEV, and it grants no new identity or write authority.

Deterministic source+plan+Markdown vertical tests prove the simple opt-in
preflight rejects dropped/duplicate candidates and reference/destructive plans
before writes, while a valid reviewed synthetic plan still writes canonical
Markdown through ordinary Core. F14 writes the two independent Eric/Luis facts
but reports its third `él` candidate as pending rather than declaring the
entire message completed. The mapping tests deliberately distinguish Core
physical fact existence from **independent semantic equivalence**, which
remains unproven without reviewed model-facing attribution and a real-model
gate. Shared-fact many-to-many grouping, positive/negative/conditional scope,
identity links, pending clarification continuation and durable replay remain
out of scope for this pilot and are mandatory before activation.

**Block 4B6 source-to-Core-plan *proposal*, opt-in/inactive:**
`odyssey_core/candidate_attribution.py` implements a separate, strictly
non-executing **Core-only Luna attribution reviewer**, injected with a Responses
client and never connected to runtime. This does not alter the accepted main
Luna Planner prompt, its original Responses JSON schema or Router v0. The
reviewer is passed the full original request, already-grounded request-local
candidates and a **separately computed validated Core RequestPlan**. It can
suggest `candidate-ID → planned Core atomic-fact ordinal` with a quoted
**exact original candidate anchor and exact planned fact text**, or explicitly
mark each candidate pending for a closed reason. A closed output schema and
independent Core-side postvalidation reject missing/reordered candidates,
invented source quotations, copied/altered Core fact text, duplicates, changed
plan/source fingerprints, ambiguous identities incorrectly marked as written,
negative/conditional/replacement scopes and unsupported reference/CREATE/
property/migration writes. A conservative unique literal token veto catches
obvious `pan ↔ leche` swaps; it intentionally rejects paraphrases without
literal evidence. All model/provider output remains `semantically_verified=false`
and `may_authorize_writes=false`: same-word evidence can never establish truth,
negation, participant identity, relative time, action lifecycle or safe
persistence, and is **not converted into a Core coverage manifest**.

Deterministic injected-provider tests cover F01 (three shared-context
activities), F11 (one shared purchase with two items), F14 (independent
Eric/Luis facts plus ambiguous third pronoun), and an F13 pronoun whose
superficially matching `cine` cannot independently prove the person identity.
The initially accepted opposite-polarity synthetic plan `No compré pan`
exposed a real missing denial check; the new Core-side negative-only veto now
blocks this exact false claim before persistence. Mixed-clause denial scope
still cannot be resolved by a lexical match and remains unverified. Vertical tests
show an injected attributor proposes the mapping with zero Markdown changes;
ONLY a separate, explicitly reviewed test claim set can pass the existing
Core coverage gate to invoke actual Core persistence in a disposable vault.
The result and fact markers are observed independently afterward. An invalid
model response never touches the vault. No network calls, key access, DEV
merge, deployment, or real-user note edits occurred in this step.

**Outstanding semantic acceptance:** Real GPT-5.6 Luna/low attribution quality
on the frozen held-out source→Core facts (and independently verified Core
identity/reference/time and contradiction rules) has NOT been demonstrated.
The separate model-facing prompt must have its own reviewed, explicitly
cost-bounded live evaluation; earlier platform security blocks must not be
circumvented. In addition, the attribution proposal must not be wired as the
execution preflight's `candidate_coverage_factory` merely because it has
grounded literals. A Core-owned semantic decision/review policy for
positive/negative/conditional assertions, identity, reference/relationship
writes, broader candidate↔fact cardinality, and durable pending continuation
remains required. Router v1 is **not ready for DEV activation**.

**Block 4B7 conservative semantic veto at Core preflight (isolated; NOT active):**
`odyssey_core/candidate_semantic_veto.py` is now called both by the separate
attribution proposer validator and by Core's **opt-in** coverage preflight,
**before** the existing write executor. This closes the demonstrated loophole
where even an externally/manual-reviewed `candidate-1 → leche` swap could pass
structural coverage and trigger a write. The bounded Unicode/accent-folded
lexical veto requires a candidate-distinctive original source token to remain
in the planned fact, disallows a newly invented denial token (Spanish/French/
English common `no/nunca/jamás/not/never/ne/pas/jamais`) never present in the
whole original request, and refuses any candidate whose source context
includes an unresolved `reference` role until **Core-verified** identity evidence
is available. Generic subjects (including project/vehicle/document) remain
eligible; the guard never assumes that subjects must be Person notes.

These checks only **reject** obvious errors. Positive results remain
`semantically_verified=false`; a negation present in a different original
clause cannot yet be safely scoped without independent source interpretation,
so a deliberately constructed cross-clause contradiction can still pass the
lexical veto. This failure boundary is captured in tests and **does not confer
write permission from the model proposal**. Stronger polarity, role, temporal
ownership, pronoun/link and source/fact meaning validation remains necessary.
The new guard is implemented only in the default-disabled experimental
Core coverage arguments; ordinary Router v0, the existing Core planner prompt,
canonical schema, DEV, production and all user notes are unchanged.

**Remaining Block 4B before any DEV activation:** an explicit, reviewed
Core-owned verified candidate→plan/fact attribution and pending clarification that
preserves independent/ambiguous partial outcomes and replay semantics; source
coverage and condition/polarity/correction ownership checks; generic shared
transaction semantics; request-detail diagnostics within approved budgets; and
additional provider-free Router→Temporal→Core→disposable Markdown tests with
Core-verified candidate attribution. The new disposable persistence tests prove
existing Core mechanics with **frozen handwritten plans**, not the actual Router
v1 provider/planner handoff through to those writes. Do not
map candidates to existing disjoint v0 `Route` objects or turn lexical inheritance
into `depends_on` (which is canonical-write dependency). Version and review the
new GPT-6 Luna model-facing contract, obtain an allowed, separately budgeted
focused live semantic gate, and only then activate in isolated DEV with rollback.
No Sol/cache changes or real-vault deployment are part of 4A.

## Open decisions before implementation (do not silently settle)

1. **Multi-unit outcomes — USER APPROVED:** persist validated independent facts even if another candidate remains ambiguous; block/defer the ambiguous/dependent fact and seek targeted clarification, as in existing clarification UX. Any interdependent candidate with uncertain grounding stays fail-closed. This is product direction, **not yet implemented**; exact concurrency/replay/write preflight remains an implementation proof obligation.
2. **Future plans and negative/conditional assertions:** which of F17/F19/F20 are persistable facts versus proposals/intentions needing confirmation, or task/event lifecycle ownership? Candidate splitting can be agreed without deciding storage semantics. Recommend leaving final assertion/target choice to Core and capability policy rather than Router.
3. **Source anchor representation:** exact substring + occurrence discriminator resolved locally, or a provider-generated offset rejected unless independently checked? Unicode/duplicate wording and backward/forward scopes require a reliable, small closed contract. Recommend provider emits literal source evidence plus disambiguation, local validator calculates offsets; defer exact schema choice to block 4.
4. **Retention/size for diagnostics:** the 30-day / 500-record actor-local checkpoint policy is approved and implemented on the feature branch; production capacity and any future activation remain open, without weakening validated stage/flow budgets or creating a new authority.

**Next gate:** human review of the above open decisions and fixture, then explicit approval before implementation; do not merge/designate the v1 behavior active based on design-only checks.
