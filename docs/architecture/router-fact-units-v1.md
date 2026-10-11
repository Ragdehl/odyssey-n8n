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

The original 26-case/56-unit [**v1 historical design oracle**](../../benchmarks/application_router/fact_units_v1.design.json) is immutable. The 22 original **human-agreed design examples**, four additional generic-subject cases (F23–F26), and the approved sequential-contacts counterexample F27 now live in a separate [**v2 approved design matrix**](../../benchmarks/application_router/fact_units_v2.design.json). They are **future expected semantic decompositions**, not predictions of current Router v0 or passing production model tests. Each case defines the source, expected number and meaning of candidate units, context edges, and a safety caveat. Do **not** weaken historical frozen Router v0 regressions to match this unimplemented v1 direction. When implementing, version and test a new model contract, replay the 22 examples with a production-equivalent Luna/low live gate, and add permutations/adversarial probes without overfitting to literal phrases.

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
| F14 | one Eric+Luis conversation statement, then ambiguous `él` | 2 | one event with two canonical participants, no assumption of simultaneity; pronoun remains unresolved |
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
| F27 | spoke to Eric and **then** Luis; afterward `él` is ambiguous | 3 | explicit sequential source separates conversations; pronoun still unresolved |

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
Core escalation result with **zero writes**. F27 checks that the ambiguous
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
duplicate their facts, and F27's two resolved source clauses may be written
without turning the ambiguous final `él` into a canonical link. These are
**hand-authored Core plan** scenarios; they do not prove Luna produced such
plans or that group links/semantic ownership are accepted in production.

The adjacent `odyssey_core/candidate_write_observation.py` creates a bounded,
read-only receipt from **actual Core** `ActionResult`/`UnitResult` statuses and
Core's real write fact ordinals, rejecting mismatched action indices, duplicate
unit outcomes and a different original user source. It intentionally marks
**every** source candidate `unattributed`: neither candidate ordering nor
Core unit/fact counts prove a source candidate was durably persisted. In F27,
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
Markdown through ordinary Core. F27 writes the two explicitly sequential Eric/Luis facts
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
activities), F11 (one shared purchase with two items), F27 (sequential
Eric/Luis events plus ambiguous third pronoun), and an F13 pronoun whose
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

**Block 4B8 narrow Core canonical-reference handoff (isolated/inactive):**
`odyssey_core/candidate_reference_handoff.py` reuses the existing
`CanonicalReferenceEvidence` produced **only after an actual successful Core
write and persisted canonical wikilink** and the existing
`_dependent_evidence_is_current` dual-guard validation. It does not resolve
an entity, allocate IDs, create another model prompt or modify runtime. For
one simple source layout (candidate 1 with one exact named subject/object/
participant role, followed immediately by candidate 2 with one original
`reference` role), it can return a **Core-private** freshness-checked carrier.
It requires one actual Core predecessor action and one unique canonical
reference proof, an exact original antecedent named-role occurrence and a
reference word inside the second candidate's own original source span. The
carrier can furnish the **existing** `DependentReferenceGuard`, which rechecks
both the persisted source fact and target Note before any later write. It
never exposes canonical IDs/guards through UI request details or accepts
natural-language source candidate evidence as a substitute for persisted
Core identity. The case F13 `Eric → él` succeeds with a **human-reviewed**
second plan on a disposable vault and a real Core canonical link; F14's
`Eric y Luis → él` stays unresolved even if only Eric's earlier note happened
to be persisted. Corrupted source/target Markdown, multiple named roles,
unscoped reference words and changed identities abstain; the existing
preflight guard independently rejects a once-valid carrier after staleness.

**Important boundary:** this is proof of **one Core canonical target identity**,
NOT proof that an unverified candidate's `él` linguistically refers to that
target. Tests deliberately inject a reviewed antecedent and dependent plan;
no real Luna semantic coreference gate has passed. The first simple candidate
has to have actually persisted a Core reference, so this does NOT impose
persistence ordering on ordinary shared dates, group continuity or subjects;
those stay request-local interpretations. An antecedent without persisted
proof or more than one plausible source candidate remains pending. Do not
activate this optional bridge, the experimental coverage write path or a
`candidate → canonical identity` graph label based only on these tests.

**Block 4B9 in-memory pending-source projection (isolated; NOT deployed):**
`odyssey_core/candidate_pending_projection.py` now projects candidate-level
pending items **only from the original validated Core source, validated
candidate coverage manifest, actual opt-in partial `ApplicationResult`, and
canonical Markdown fact readback**. It contains a read-only pending original
source anchor (e.g. F14 `Mañana iré al cine con él`), closed pending reason,
request ID, physical fact count, and explicit
`persisted=false`, `resumable=false`, `candidate_semantics_verified=false`.
It refuses mismatched request IDs, altered sources, unsupported source shapes,
or an attempt to reinterpret a plan/fact verification failure as a missing user
clarification. Tests cover real disposable Markdown from F27's two explicitly separate
written facts and one ambiguous third source candidate, inconsistent evidence,
no pending candidate, and no accidental durable pending/knowledge writes.

**Block 4B10 approved candidate pending state / guarded continuation (isolated):**
The human approved storing source-candidate clarifications under existing
actor-local pending operational state until resolved/cancelled, interpreting an
immediate answer only when the conversation has exactly one outstanding
clarification, requiring an explicit request selector for multiple/unrelated
turns, and never undoing already persisted independent Core facts on
cancellation. Implementation uses `state/pending/candidates/<request_id>.json`
format `odyssey_pending_work` version **2**. Keeping a dedicated subdirectory
beneath the existing Phase-17B pending root leaves v1's `list_ids()` and
validated incomplete-`RequestPlan` records byte-for-byte unchanged. It adds
NO canonical Note type, database, index, service or new mutation authority.

`odyssey_core/candidate_pending_projection.py` now carries real Core source
anchors (including scoped original `reference` wording), physically verified
request/ordinal/note-id/normalized-fact-digest markers and candidate pending
reasons. In the **opt-in** application boundary, `candidate_pending_recorder`
runs only after the normal approved subset was written and canonically read
back; it records with a request-bound create-only, fsynced/locked v2 store or
returns a truthful `persisted=false` partial result on failure. The format
preserves an offset-bearing capture timestamp so a resumed `mañana` does not
silently shift to the date of the eventual user answer. Record sizes/counts
are bounded, malformed/symlinked/stale evidence fails closed; completed Core
facts are NOT converted into replayable instructions.

The v2 store reuses Core's existing bounded `ClarificationOption`, direct
reply matcher, optional injected Luna clarification classifier and canonical
`current_identity_guard`: one trusted immediately-following `Con Luis`
selects only an **existing Core-grounded** `Luis` choice; explicit `cancelar`
closes pending state without deleting a Note; an unrelated new request does not
consume it; multiple open requests require an explicit original request ID;
answer request IDs are replay/idempotence guards. Modified selected notes OR
changed previously written facts make selection/continuation stale, with no
silent repair/replay. The typed selected state is rechecked upon every later
Core use and supports generic canonical Note types, not only Person. Records
are kept until cancellation or eventual proven completion; there is no
speculative age-based expiry. Missing Core-verified options remain open but
cannot execute or choose an invented identity.

`odyssey_core/candidate_continuation_guard.py` offers a narrow **Core-only**
last-moment preflight for an already selected identity, one reference-bearing
fact and one ordinary reference-only helper. It requires that the original
source reference mention and current option guard exactly match Core's
resolved target ID. With a **pre-reviewed synthetic plan** and the captured
clock, the real Core writer now persists *only* the dependent cinema Day fact
linked to Luis in a disposable vault, leaving both earlier independent facts
unchanged. A wrong target/person, changed canonical Note, altered pronoun,
extra write or canceled clarification is rejected before persistence. This
success does NOT mean the model can yet generate the correct continuation:
semantic event/date/polarity/source-fact equivalence and safe completion still
need a separate live model evidence gate and Core review. The v2 state is left
`selected` (not falsely `resolved`) after this simulation, and the guard never
turns a user reply directly into a `RequestPlan`. No runtime request path
supplies these experimental arguments; DEV and PROD remain Router v0.

**Initial explicitly authorized live smoke evidence (2026-10-10; NO deployment):**
The user authorized 3–4 focused synthetic cases, a small measured cost and no
real-vault writes. A one-shot transient **user systemd** unit loaded only the
existing fixed `EnvironmentFile=/home/ragdehl/.config/odyssey/secrets.env`;
the remote shell never loaded or printed credentials. The remote shell lacked
its default `XDG_RUNTIME_DIR` despite the ordinary user bus running; using the
standard `/run/user/1000` session path restored the **same authorized** user
service-manager transport. No credential, account/network permission, Docker,
Cloudflare, NoteSchema, runtime or user-vault changes were made.

A provider-free dry-run first exercised the same bounded input/schema envelope.
The live gate enforced `store=false`, `low` effort, two exact allowed models,
SDK automatic retries **zero**, max seven calls and **$0.05 USD** in conservative
per-call input-bytes/output-token ceilings; it skipped any candidate-provider
follow-up when Router's actual output did not satisfy the expected unit/state
cardinality. Actual completed requests: **six** (4 Router GPT-6 Luna/low,
1 Core-attribution GPT-5.6 Luna/low, 1 Core planning GPT-5.6 Luna/low).
Recorded model usage: **13,233 input** and **2,606 output tokens**; estimated
maximum *standard-rate* charge under the 2026-10-09 pinned price snapshot is
**$0.004006 USD** (cash invoice and caching discounts not measured). The unit
finished successfully. These are observed *model* results, not code-generated
fixture answers, and no Core writes or personal data retrieval occurred.

| Frozen case | Live Router v1 result | Independent Core model result |
| --- | --- | --- |
| F11 `Hoy compré pan y leche.` | Two purchase items, expected count/state correct | Core-attributor passed local exact source/fact validation; Luna Planner returned structurally valid 1-action `RequestPlan` (not executed or independently checked for semantic correctness) |
| F14 `Ayer hablé con Eric y Luis. Mañana iré al cine con él.` | **Two** units vs oracle's **three**: grouped Eric+Luis as one occurrence, separately marked `él` as `ambiguous_identity` | Core attribution deliberately **skipped** after unit-count mismatch |
| F01 park → cinema → concert | Three separate units with distinct lexical temporal scopes, expected states/count correct | Not run in this tiny gate |
| F13 Eric → `él` → pan | Three units with original reference role, expected states/count correct | Not run in this tiny gate |

**Acceptance verdict: FAIL / insufficient for DEV.** F14 exposes a real
contract-or-oracle mismatch: the current Router prompt produces one coordinated
conversation mentioning two people, while the existing design oracle expects
two independent source candidates. It is *not* a hallucinated Core link—`él`
remained ambiguous—but its partial success cannot satisfy the existing three-
candidate coverage and continuation assumptions. Whether a coordinated
multi-participant *single conversation* ought to be one event with two
canonical participant references or two independent atomic facts is a **product
semantics decision**; do not silently change the oracle or overfit the prompt
to reach three units. If two facts are required, update the model teaching
contract and run a **new separately reviewed frozen held-out gate**. The tiny
smoke (4 cases) also does NOT replace the required full 22/26-case model
regression, real provider-produced continuation, polarity/identity evaluation
or the existing historical release gates. User-facing tests in DEV remain
blocked until these are resolved; no more provider calls were attempted.

**Block 4B11 approved source granularity and bounded canonical participant pilot
(2026-10-10, feature branch ONLY):** The user approved the more general
**one coherent event with multiple participants**, never "one fact per name"
or "one candidate per verb". In particular, "Ayer hablé con Eric y Luis" is
one assertion with two independent canonical links; it does NOT imply the
people were together or conversations happened simultaneously. A true
source-temporal distinction ("hablé con Eric y **después** con Luis") yields
two independently managed events. Separate subject properties (F09), tasks,
negative assertions, purchase-item facts and changed dates/times continue to
split when their truths/actions are independently manageable. Source sharing
must not erase independently correctable properties or group-member links.

The **approved v2 F14** has 2 source candidates (one shared event with exact
`participants` source "Eric y Luis", and a separate ambiguous future cine
plan). The formerly expected 3-candidate decomposition is preserved as **new
F27** with **explicitly sequential** wording; no existing split, pronoun or
pending/replay safety test was deleted to change the oracle. The v1 frozen
matrix and its benchmark acceptance tests remain entirely unchanged; active
v2 design tests use **27 cases, 58 candidates**. No prompt, Structured Outputs
schema, NoteSchema, Router v0, runtime composition or DEV deployment changed.

Core's ordinary canonical writer already supports one fact with two typed
`KnowledgeReference` helper lookups. `odyssey_core/candidate_multi_participant.py`
now admits only the narrow source-anchored shape of **two explicit named
participants joined by ' y '**, with one fact and exactly two non-mutating
Core reference lookup helpers (including type-generic project Notes). Extra,
omitted, swapped, duplicate or mutable helpers are rejected **before writes**
by the opt-in candidate coverage gate. Core still has exclusive canonical
identity/target/write authority; grouped lexical source alone cannot prove
identities or event meaning.

`candidate_fact_readback.py` now verifies physical persistence of both
Core-rendered canonical wikilinks using the **existing Core private
post-write CanonicalReferenceEvidence dual guards**, exact request ID/fact
ordinal/note ID/text and canonical target path/name, including stale target
and tampered Markdown failures. It stores only the digest of the rendered
verified fact (not transient `{{ref:N}}` input placeholders), allowing the
already-approved v2 pending workflow to detect later edits without rejecting
legitimate grouped links. The Core opt-in test can write F14's single linked
conversation **and** durably preserve its ambiguous second source candidate;
"Con Luis" is captured and a separately reviewed, narrowly guarded Core
continuation writes ONLY the future cinema fact. Previously written Markdown
is unchanged. Graph/Notes backlinks independently confirm exactly one
conversation occurrence accessible from both Eric and Luis. A parallel
**project** test links Odyssey and Atlas through the same Core contract.

**Non-authority and rollout boundary:** Only the frozen *reviewed* tests build
these Core write plans. The separate Core Luna candidate-attribution proposer can now accept this
narrow source-grounded linked plan **only as a non-authoritative proposal**;
its output explicitly remains `semantically_verified=false` and
`may_authorize_writes=false`. The main Luna planner has not demonstrated it
can emit that plan unaided. Ordinary runtime does not enable this opt-in path. These tests
do NOT show that Luna generates grouped canonical links, detects the correct
pronoun identity, scopes future dates, fixes corrections, or closes the pending
record on semantic confirmation. The current pilot handles only two explicit
"A y B" named mentions; relationship-bounded groups such as "mi mujer y mis
hijos" need ordinary broader Core identity semantics, not simplistic name
splitting. No live provider calls were made for the approved-oracle update.

**Interpretation of the earlier bounded live gate:** The six real calls and
measured `$0.004006` estimate are unchanged historical observations. At the
time, F14 had a **3-candidate** oracle and the GPT-6 Router gave **2** units,
which was a reported disagreement. After human adjudication, the count and
ambiguous-identity *state* agree with the new two-candidate oracle; the model
called its future clause `plan` whereas the current fixture says `occurrence`,
and the smoke did NOT test its canonical links or semantic Core continuation.
This is an **oracle correction, not proof of a newly passing live quality
regression**. F27 has not yet had its own live gate. Re-run the broad frozen
27-case real-model gate only after final source/plan contracts are reviewed.

**Block 4B12 non-authoritative model attribution for two canonical links
(2026-10-10, isolated; NOT live-model validated):**
`odyssey_core/candidate_attribution.py` now reuses the *same Core-only
source-anchored two-named-participant checker* as the experimental Core
coverage gate. After Core has independently produced a validated linked
`RequestPlan`, it can submit that plan's **one** exact placeholder-bearing
atomic fact to its existing, separate GPT-5.6 Luna/low read-only attribution
proposal (without modifying the strict output JSON schema, prompt text,
main Luna Planner or Router). It requires exactly one group candidate able to
justify the plan's two reference-only helpers; cannot treat helpers as extra
facts; rejects an omitted, duplicated, mutated or incorrectly targeted helper;
and refuses to credit that planned ordinal to any different candidate. The
model still only proposes source-span and fact-ordinal correspondence.
**Semantic equivalence/identity/date/polarity remains unverified; the model
has zero write authority and cannot construct or submit the Core coverage
manifest.** Provider-fake tests confirm this proposed grouped event, the
separate ambiguous pronoun, no persistence/execute method and fail-closed
invalid reference plans. No new paid calls and no DEV/PROD wiring or model-
facing prompt/schema/hash changes occurred; a dedicated production-shape live
quality gate is still mandatory before enabling this experimental route.

**Block 4B13 real Core Luna compiler + pending Temporal correction (2026-10-10,
feature branch only, provider-free):** The first model-shaped semantic PLAN for
F14 exposed a concrete integration blocker, invisible to manually constructed
Core plans: Temporal supplies BOTH `Ayer` and `Mañana` to the full-source Luna
planner, but its two existing strict Core validators required EVERY exact
mention to be consumed by the partial safe WriteAction. That incorrectly
rejects an independently safe conversation write while an ambiguous future
cinema clause is deliberately pending. No model prompt edit solves this
validation conflict.

`odyssey_core/experimental_luna_planning.py` now has a default-disabled,
**Core-owned pending Temporal exception** restricted to a passed
`CoreCandidateContext` already independently source-validated. Exactly one
Temporal text occurrence may be exempted from *that plan's completeness
validation* ONLY when its exact span is wholly inside the sole candidate
covering it, that candidate is explicitly `ambiguous_identity`, and it also
cites the same exact span through a temporal source role. Missing dates in
normal, unrelated, overlapping, unscoped or repeated literal occurrences
still fail closed. A filtered immutable **validation copy** of the Temporal
domain is used for the existing Core plan validator and fact-anchor binder;
the originally supplied Temporal interpretation and its date/time values are
never changed, normalized by Router, or turned into identity/write authority.
Without candidate context the previous Luna and Core validators remain
strict and the prompts, Structured Outputs schemas, cache-stable prefix,
normal Router v0 runtime and production paths are unchanged. A successful
source-only exception is **not** semantic attestation: opt-in Core candidate
coverage remains an independent mandatory pre-write gate.

Most importantly, a frozen provider-shaped GPT-5.6 Luna semantic WRITE fixture
now runs through **the actual `OpenAILunaExperimentalPlanner.plan` +
`decode_semantic_write_action` + `compile_semantic_write`**, rather than
injecting a hand-authored `RequestPlan`. Core itself produces `calendar_day`
10-03 with exactly one fact `Hablé con {{ref:0}} y {{ref:1}}.`, two typed
`reference_lookup_only` person helper units with canonical `identity` roles,
and verified `2026-10-03` fact temporal anchors; Core's unchanged writer,
source review, canonical dual-link physical readback and durable v2 pending
state then run in `tmp_path` with the exact 10-05 cine clause withheld.
The grouped candidate checker now recognizes Core's generated `identity`
reference role as well as its earlier fixture role, still requiring full
canonical helper resolution and no additional side effects. Injected model
output is a **test fixture** and no live-model semantic quality evidence has
been obtained for F14 or the new F27. Separate negative tests prove that a
missing **safe** past date, selecting the wrong target Day, repeated ambiguous
`Mañana`, omitted temporal role or absent candidate context cannot bypass
Core's Temporal proof obligation. Existing source/plan/fact/wiklink proofs,
polarity and pronoun authority remain mandatory. No paid provider calls,
DEV/PROD writes or schema migration occurred in this block.

**Block 4B14 provider-free narrow cost preflight (2026-10-10):** A prior
large inline command trying to author a live provider script was blocked by
the platform before reaching the Pi; no script was created, provider call
attempted or cost incurred. This is **not** evidence of an OpenAI API failure,
and the reason for the platform block is unknown. Without repeating that
operation through a different transport, a **distinct offline-only** request
envelope audit now lives at
[`benchmarks/fact_candidate_v2_preflight/`](../../benchmarks/fact_candidate_v2_preflight/README.md).
It uses existing Router, Temporal, Luna and candidate-attributor request
constructors with fake clients on F14/F27/F09/F10 to enumerate exact input
payload bytes, model, effort, strict-schema setting, `store=false` and output
limits; it cannot import the SDK or access provider credentials.

Under the pinned 2026-10-09 rate snapshot and a deliberately conservative
pre-call input envelope (`2 * complete request JSON bytes + 200` tokens,
maximum input/cache-write rate plus full capped output), **all 9 proposed
calls have an estimated upper envelope USD 0.0848571** and do not fit the
previously approved USD 0.02 ceiling. The 6 Router/Temporal calls alone have
an upper envelope USD 0.013495, leaving the two Core Luna evaluations and
one attribution outside that conservative first wave. This is a **possible
reviewed plan**, not a live-model result or an alternate way to bypass the
blocked platform operation; a distinct security-permitted execution procedure
is still required. Offline-only tests freeze model settings, call ordering,
budget arithmetic and the strict no-network/no-credential separation. The
user's authorized USD 0.02 ceiling is respected; do not silently expand it.

**Block 4B15 explicit sequential events F27 with Core references (2026-10-10,
feature branch ONLY, provider-free):** Real (fake-provider) Core semantic
compilation for `Ayer hablé con Eric y después con Luis. Mañana iré al cine
con él.` produces **two distinct atomic facts in one dated Core write unit**,
`Hablé con {{ref:0}}.` and `Después hablé con {{ref:1}}.`, plus **two different
reference-only helper units**. This is intentionally NOT the F14 one-event
multi-participant case. A bounded Core-only checker requires the precise
source `hablé con Eric y después con Luis`, original distinct Eric and Luis
anchors, the source predicate and date roles for BOTH candidates, strict fact
order/templates, identical justified fact dates, exact named helper selections,
and an independently source-anchored ambiguous future `él`. Omitted/swapped
references, reversed facts, extra helpers, lost temporal scope, edited source
sequence and missing pronoun reference evidence fail **before any write**.
This is a first narrow regression shape, not a universal Spanish grammar rule.

Core candidate coverage and the untrusted Luna source/fact attribution
proposer both accept these two *separate* referenced facts after their own
Core validation; neither acquires semantic-certification nor write authority.
The canonical fact readback now binds **each fact's referenced subset**, not
incorrectly demanding every reference in a multi-fact Core unit be repeated
in every fact. All actually used links still require guarded Core identity
and source-note content evidence, exact Markdown markers and exact fact
strings. Using an isolated vault, both conversation facts and both backlinks
are physically verified, the future cinema stays in durable v2 pending state,
then `Con Luis` writes only the future cinema fact without touching the
original. Editing the source Day (even only one link) invalidates both facts'
source-note content guards, deliberately failing closed. As before, model
outputs in this test are explicitly frozen deterministic fakes, NOT real
GPT-5.6 Luna model acceptance. No new provider calls, DEV/PROD wiring,
model-facing prompt/schema change or user-vault writes occurred.

**Block 4B16 selected-continuation whole-plan preflight (2026-10-10,
feature-branch-only):** The former `SelectedCandidateWriteGuard` checked one
Core write action's resolved identity immediately before that action, but
another `RequestPlan` action could write before/after it, and the guard had
not established that the saved future event/date was preserved. A narrow
request-level check now runs **before the action loop or history snapshot**,
only for injected guards exposing `validate_request_plan`; normal app/Task
Core guards keep their previous contract. Rejection returns an empty
`NEEDS_ATTENTION` result and no writes; later identity/source-note checks
remain active at resolved-target preflight. The opt-in v2 selected guard
requires exactly one `WriteAction` with one dependent cinema fact and one
canonical lookup-only helper, the exact reviewed `Mañana iré al cine con él`
source candidate, no unsupported additional actions/limitations, and a
`calendar_day` target + one date-only Temporal anchor equal to the **day after
original offset-aware capture time**, even if the human answers much later.
The exact `Iré al cine con {{ref:0}}.` pattern is purposely limited to this
F14/F27 proof, not a general source-semantic equivalence engine. Existing
canonical choice proof still verifies Luis at the last moment. Regression
sentinels reject extra writes and reads, wrong activity, lost/shifted date,
changed targets/source evidence and inserted facts **before any mutation**,
while the permitted continuation still produces exactly one disposable Day
fact without replaying previous events. Core note/event semantics remain
unverified for broader natural language; durable `selected` state is still
NOT marked completed automatically. No provider calls, model switch, DEV or
PROD deployment.

**Block 4B17 duplicate source candidate guard (2026-10-10, feature
branch ONLY, provider-free):** The untrusted Router v1 source validator
formerly allowed a model to return two otherwise identical candidates with
different request-local ordinals. A narrow structural guard now rejects
duplicate kind/state and identical **locally resolved exact source occurrences,
roles and inheritance edges** before passing anything to Core. It compares
normalized role ordering, so shuffling model output arrays cannot make an
identical assertion appear independently grounded. Two legitimate candidates
that share a predicate but have different subject anchors (F09), two item
facts in the same purchase (F11), a shared two-participant event (F14), and
two separate sequential events (F27) still pass. Identical words appearing
in two distinct physical source occurrences also remain distinct. The
adapter reports invalid source evidence without making a Temporal/Core call.
This is **duplicate-structure prevention, not semantic deduplication**: two
differently anchored candidate proposals may still express the same claim,
and no local rule has proven complete semantic coverage of arbitrary messages.
Prompt/schema, identity policy, canonical writes, and live-model configuration
remain unchanged; tests use fake provider outputs only.

**Block 4B18 source-occurrence-safe Temporal alignment (2026-10-10,
feature branch ONLY, provider-free):** Temporal's existing interpretation
emits ordered text mentions without occurrence indices. The first-match-only
Router→Temporal bridge could silently attach one returned `Mañana` to the
first of two distinct literal occurrences, even when the provider did not
specify which event it meant. The bridge now compares the earliest and latest
**non-overlapping ordered** alignments against the unchanged original text.
If either alignment differs, the requested occurrence is not uniquely
identifiable and source binding raises a closed `RouterError` before Core
planning or any write. Two explicit identical mentions still map to their
respective first/second source positions, including multi-event day scopes,
and distinct unique date expressions remain unchanged. An absent Temporal
interpretation still preserves missing/unknown states. This check does not
normalize time or grant semantic authority: textual uniqueness is necessary
but is not evidence that the model's date resolution is semantically right.
Deterministic adapter and Router→Temporal fake-provider tests cover repeated,
partial and fully disambiguated cases. No model-facing prompt/schema change,
live provider calls, DEV/PROD activation or vault access.

**Block 4B19 observed synthetic GPT-6 Router-only v2 gate (2026-10-10,
feature branch ONLY):** The separately versioned, snapshot-pinned
[reviewable runner](../../benchmarks/fact_candidate_v2_live/README.md)
was accepted through the ordinary existing user systemd service and made
**four** real GPT-6 Luna/low Responses calls with `store=false`, no retries,
and **no Core, Temporal or vault writes**. Its hardcoded cases were F14, F27,
F09, F10, and its conservative four-call pre-reservation was **USD
0.01181875**, below the previously authorized USD 0.02. The observed
usage was **2,134 input + 1,575 output tokens**; under the pinned standard
rates this is **USD 0.0010009 estimated**, not a billed total. All four
provider responses completed and passed the closed local source shape
validator. The untouched original prompts/model/schema were tested.

The new [saved synthetic provider outputs](../../benchmarks/fact_candidate_v2_live/results/20261010T185618Z.json)
plus offline replay regression tests demonstrate:
- **F09 FAIL (semantic):** `Marta y Luis viven en Lyon` was emitted as **one
  `relationship`**, rather than independently manageable Marta/Luis
  residence properties.
- **F10 one-event meaning correct:** `Marta y Luis se conocieron en Lyon`
  was emitted as one `relationship`. Its source spans differ from the
  exact approved oracle, but source evidence was grounded; an exact-fixture
  mismatch is not by itself a semantic failure.
- **F14 partial:** coherent Eric+Luis conversation + ambiguous future
  `él` (two candidates) was correctly counted, but the future kind is
  `plan` rather than the approved `occurrence`; `Ayer`/`Mañana`
  were labeled `time`, and Core's independently reviewed grouped
  canonical reference preflight rejects the emitted participant evidence.
- **F27 partial:** the two source-explicit sequential contacts + ambiguous
  future are correctly separated (three candidates), but future kind
  is `plan`, dates are `date_scope`, and `él` lacks the explicit
  `reference` role; Core's sequential contact coverage preflight rejects
  the unresolved pronoun representation.

The strict offline oracle comparator reports a **fixture FAIL for all four**
due to source anchors/roles/kinds, but only F09 currently establishes a
clear incorrect underlying event/property segmentation. We must not conflate
strict token-span equivalence with semantic correctness. The safeguard
failures for F14/F27 are observed by replaying **the real model Router JSON**
against already-reviewed synthetic Core plans and guards in an isolated
no-write context. No normal Router runtime switch, prompt tuning, model
migration, real user vault access, or DEV/PROD deployment occurred. The
model-quality gate is **FAIL / NOT READY**, and the explicit normal-user
service execution here does not retroactively authorize repeating any
previously blocked remote operation.

**Block 4B20 first reviewed prompt revision — real GPT-6 evidence (2026-10-10,
feature branch ONLY):** After the original F09/F10/F14/F27 live gate,
`OpenAIFactCandidateRouter` gained a **v2 prompt extension behind an opt-in
constructor argument**, inheriting the entire prior v1 prompt unchanged.
The JSON schema, Core, Temporal, Router v0 and model configuration are
unchanged. Frozen requests are in
`benchmarks/fact_candidate_v2_live/prompt_v2_requests.json`.
A separately reviewed four-call GPT-6 Luna/low gate completed using the
ordinary existing user service and only synthetic text, with
`store=false` and SDK retries disabled. Conservative v2 reservation was
USD 0.01379775; recorded usage was **3,634 input and 1,389 output tokens**
(USD **0.0010579** estimated at pinned standard rates, not the invoice).
With first-wave observed cost USD 0.0010009, the two focused runs total
approximately USD **0.0020588**, within the authorized USD 0.02.
Raw results are frozen at
`benchmarks/fact_candidate_v2_live/results/20261010T191859Z.json`.

Compared with the first v1 GPT-6 run:
- **F09 improved materially:** two independent `property` assertions,
  anchored to Marta and Luis separately, rather than one `relationship`.
- **F10 retained one mutual event but REGRESSED its kind:** `occurrence`
  instead of the approved `relationship` for `se conocieron`. This is a
  model-facing classification error, not a new duplicated event.
- **F14 improved:** one grouped contact and an ambiguous future
  `occurrence`, exact `date` roles for Ayer/Mañana and
  `reference` for `él`. The first grouped fact cites separate
  `participants` name spans, which is valid literal evidence, but the
  narrow opt-in Core pilot currently requires one contiguous `A y B`
  participant span wholly contained in a source anchor. Core still
  rejects the offered source shape before writing.
- **F27 improved:** two ordered contacts and an ambiguous future
  `occurrence`, an explicit `reference` for `él` and exact
  `date` roles for the first and third candidates. The middle event
  inherits the earlier predicate without an explicit `date` role,
  and the pending candidate uses multiple source anchors rather than
  one enclosing its pronoun. The narrow opt-in Core pilot rejects this
  shape before any write.

These results **must not** be described as four passing Core integrations.
The model understands the principal event distinctions better, while exact
fixture comparison and Core source-coverage readiness remain **FAIL**.
Not all exact-span mismatches are semantic misinterpretations: a future
review should decide whether a general Core-owned source evidence validator
can safely accept independently grounded equivalent spans/role inheritance,
rather than prompt-overfitting to narrow handwritten pilot templates.
Preserve the strong canonical reference/temporal guards. No DEV/PROD
activation, real Notes, schema or model migrations occurred.

**Block 4B22 third real focused GPT-6 Router gate and source-safe handoff
(2026-10-10, feature branch ONLY):** A narrowly opt-in v3 teaching suffix
preserves the complete prior v2/v1 prompts and gives a general rule distinguishing
a reciprocal `relationship` from a multi-participant `occurrence`.
Exactly **four synthetic GPT-6 Luna/low Responses calls** completed with
`store=false`, no SDK retries or personal data. The exact reviewed input
snapshot is `benchmarks/fact_candidate_v2_live/prompt_v3_requests.json`
and saved outputs are `results/20261010T193754Z.json`. Observed usage:
**4,238 input / 1,506 output tokens**, standard-rate estimated
**USD 0.0011768** (not invoice). The three focused runs together consumed
an estimated **USD 0.0032356** under pinned rates; v3's conservative
pre-call envelope was USD 0.01464675, and its previous-observed-plus-new
worst-case reservation was USD 0.01670555, below the originally authorized
USD 0.02 total.

**Meaning-based review of the 4 actual provider responses** now passes:
F09 yields *two separate property* candidates for Marta and Luis; F10
yields exactly *one reciprocal relationship*; F14 yields *one two-person
contact* and an *ambiguous future occurrence*; F27 yields *two separate
ordered contacts* and an *ambiguous future occurrence*. Exact `date`,
source-named `participants`, and pending `reference=él` roles remain
source-grounded. The strict oracle's exact textual-span equality still
reports mismatches for the four cases; alternative original substrings are
not automatically semantic mistakes.

The existing **inactive Core-only source evidence guards** were expanded
conservatively to accept original offsets that independently prove two
adjacent named participants, and two contacts in one explicitly successive
dated clause. Core's separate pending-state projection accepts disjoint
originally anchored fragments **only** when they are all in one bounded
source clause and include the original unresolved pronoun. Failure/negative
tests reject missing/swapped names, missing temporal/predicate/ordering
evidence, ungrounded cross-clause fragments and speculative references.
Offline replay using real saved GPT-6 **v2 and v3** Router proposals (NOT a
live GPT-5.6 Core planner) now passes Core coverage, isolated canonical
Markdown write/readback, linked Eric/Luis identities, durable pending,
explicit 'Con Luis' choice and guarded continuation, preserving the
already-written Day without duplicates. F10's separate name-roles before
a reciprocal predicate are independently source-checked by Core, but its
complete personal-Note write plan is **not** tested in this slice.

All writes were to disposable test vaults. **Router v1 remains inactive in
DEV and PROD; Core's production model remains GPT-5.6.** This focused
four-case gate cannot substitute for a held-out 23-case semantic sweep or
for a separate real Core planning and acceptance gate. No claim that
all new user messages or identity resolutions are semantically certified.

**Block 4B23 F09 physical Core write proof and F09/F10 Core provider budget
preflight (2026-10-10, feature branch ONLY):** The observed GPT-6 prompt-v3
F09 source evidence (two separately anchored `property` candidates) now passes
Core's independent candidate→planned-fact coverage and physically updates
**two existing, independently seeded synthetic canonical Person notes**:
"Marta vive en Lyon." and "Luis vive en Lyon." Markdown readback verifies
both facts and distinct stable person targets; swapped, duplicated or omitted
property assignments fail before any write. This replay uses a separately
constructed reviewed fake Core plan, **not real GPT-5.6 planner output**.
F10's one mutual `relationship` is source-grounded and Core validates its
two canonical reference helper roles; a full Core-chosen target/plan/Markdown
representation is still unverified, and no fabricated date/event Note should
be inferred from this undated source.

A separate **Core-only, offline-by-default, source-pinned** executor is
prepared at `benchmarks/fact_candidate_core_live/`. Its exact provider
request hashes and current model/schema/prompt are verified offline for
**F09 and F10 only**, using the existing `gpt-5.6-luna` / low planner,
unchanged 2048-token output cap, `store=false` and no SDK retries. It
has no repository, Core executor or personal-vault access. A conservative
**two-call reservation is USD 0.06344020**, and previous three Router runs'
standard-rate estimated cost is USD 0.00323560, implying a required new
**cumulative approval of USD 0.07**. The previous USD 0.02 Router allowance
does not cover this new worst-case gate. **The live GPT-5.6 Core gate has
NOT been executed or authorized**; only offline capture/preflight/tests
have run. After separate explicit budget approval, collect those two
actual model responses and independently verify target/cardinality,
canonical Note representation and any refusal/escalation. Do not claim
Core production-model acceptance or enable Router v1 before that evidence.

**Block 4B24 live GPT-5.6 Core F09/F10 model evidence and real write replay
(2026-10-10, feature branch ONLY):** Under explicit user approval of a
**USD 0.07 cumulative test ceiling**, the previously reviewed and
SHA-256-pinned two-call `benchmarks/fact_candidate_core_live/run_live.py`
executed via the Pi's standard approved transient user-service process.
Both `gpt-5.6-luna`/low model replies completed, returned a locally
validated `PLAN` with `store=false`, and made **NO vault writes**. Frozen
synthetic real-provider outputs at
`benchmarks/fact_candidate_core_live/results/20261010T200525Z.json`
are reusable by offline CI. Observed usage: **21,004 input + 651 output
tokens**. At the project's pinned standard non-cached rates, Core cost is
estimated **USD 0.0049820**; combined with all prior focused Router
calls **USD 0.0082176** (estimates, NOT a provider invoice), below the
new authorized USD 0.07 ceiling. There were exactly two Core calls;
no model, prompt, schema, SDK retry or production runtime change.

- **F09 real Core PLAN:** two independent `person` targets "Marta"
  and "Luis", each assigned `Vive en Lyon.`. The original subject
  occurs in Core's target, rather than being repeated inside the fact
  sentence. The previous source-veto falsely rejected this valid
  representation because it only searched fact text for the source
  subject; a Core-owned **source-person target property guard** now
  verifies the candidate's individually anchored original subject,
  exact named target, matching original location/content, absence of
  another candidate's subject in that fact, and the usual unsupported
  negation protections. Both model-generated writes succeed and are
  physically read back from two separate seeded fake Person Markdown
  notes; swaps, duplicates, changed locations and negation are rejected
  before any write.
- **F10 real Core PLAN:** exactly **one** fact `Se conoció con
  {{ref:0}} en Lyon.` on target Marta, and a **non-mutating identity
  helper** resolving Luis. This represents one mutual meeting with an
  ordinary backlink to Marta visible from Luis; it does not duplicate
  the fact on Luis's Note or invent a historic date. The phrase is
  somewhat awkward Spanish and is *not* language-quality certification.
  The old two-person grouped-event guard expected two referenced
  people and was inappropriate for a canonical fact stored on one
  person. A separate **Core-only reciprocal source relation guard**
  checks the two original named parties, exact shared `se ...`
  predicate and source location, directed target's membership in the
  pair, exactly one reference helper for the other person, only one
  fact and no unintended helper mutations. It rejects wrong targets,
  references, invented locations/dates, unrelated predicates and
  accidental duplication. F10's actual saved Core `PLAN` now
  executes successfully against seeded disposable Person Markdown,
  physically verifies the one fact and its canonical Luis wikilink,
  and confirms a backlink from Luis to the Marta fact. Reverse
  storage (Luis with a Marta link) remains source-valid.
- **Scope/limits:** These are **fixed F09/F10 synthetic utterances** and
  **existing, unambiguous seeded Person identities**. The relation
  guard is deliberately narrow for explicit two-name reciprocal
  constructions; it is not a universal relationship parser and has
  not exercised the normal singular-person CREATE lifecycle. The
  source/lexical tests are negative guards, not general truth
  certification. All physical Markdown writes are **disposable
  offline-test vaults only**, never the real user vault. Actual
  model calls returned plans but never executed them. Four-case
  Router semantic evidence still stands; normal Router v0 and
  GPT-5.6 Core production configurations remain unchanged. The
  **other 23 Router cases, full runtime activation and independent
  broader semantic Core gate** are not completed.

**Block 4B26 real F14/F27 Core semantic-refusal diagnosis (2026-10-10,
feature branch ONLY):** After the live GPT-6 Router v3 success and the
fully validated synthetic-fake Core write/readback + pending continuation,
we called the unchanged **real GPT-5.6 Luna/low Core planner** with
original whole-source F14 and F27 plus exact source-validated candidate
context and deterministic Temporal `Ayer=2026-10-03`,
`Mañana=2026-10-05`. Both provider calls completed successfully and
returned **`ESCALATE` with no actions**, not a partial `PLAN`.
This is a genuine semantic-acceptance failure, **not** a provider error,
not a failed write and not evidence that the user vault was changed.
Frozen original F14/F27 synthetic-only receipts:
`benchmarks/fact_candidate_core_live/results/20261010T202736Z-F14.json`,
`.../20261010T202803Z-F27.json`.

The probable conflict is the inherited single-request/all-intents
planning instruction (PLAN only if every material intent is preserved;
otherwise ESCALATE), while the product requires independently grounded
past facts to be saved with an unrelated unresolved future reference
durably pending. The provider's ESCALATE JSON supplies **no explanation**,
so the exact internal reason is unknown. A first **opt-in scoped-partial
prompt extension** was reviewed, hash-pinned, and tested without changing
existing default prompts, schema, reasoning, model or runtime. It explicitly
teaches: PLAN only the independently safe actions, do not guess any
pronoun, and require separate Core coverage+pending recording before
writes. Real GPT-5.6 **still returned ESCALATE on both** F14 and F27.
Frozen opt-in results:
`benchmarks/fact_candidate_core_live/results/20261010T203404Z-P-F14.json`,
`.../20261010T203640Z-P-F27.json`.
The four Core-call results are reproducibly checked by offline sentinels.
The opt-in single-call runner was corrected to distinguish original and
partial receipts when enforcing cumulative-budget and no-retry controls.

Observed four new calls: initial F14 (11,054 input, 362 output), F27
(11,131/131), revised F14 (11,290/386), revised F27 (11,367/239).
Pinned-rate estimated **cumulative focused Router+Core spending:
USD 0.01852760**, under the user's explicit **USD 0.07** limit;
not a billed total. **No further paid prompt tweaks are justified by
these results.** The previous F09/F10 real Core acceptance holds and
the saved F14/F27 fake-provider physical writes are still valid *only
as mechanical integration tests*. Router v1 still inactive everywhere.

**Proposed next architecture experiment (not implemented or authorized
as a production behavior):** Core—not Router or Calendar—may create a
conservative, read-only source-scope preview for independent original
clauses, retaining their exact offsets, the complete untouched source,
Temporal's validated dates and every unresolved candidate. A second
Core-only planner pass could then consider only the independently
safe scope, while any correction, negation, conditional, cross-clause
dependency, shared temporal ambiguity, uncertain identity or insufficient
provenance must fail closed. The full original candidate-to-plan coverage
gate remains mandatory, as do physical readback and durable pending
before claiming partial success. Do **not** simply truncate the prompt
at the first full stop or treat Router's model classifications as
write authority. No production source scoping, system prompt rewrite,
model switch, deployment, schema mutation or real vault write has
yet occurred.

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


**Block 4B27 Core-owned per-unit handoff preview (2026-10-10,
feature branch only, provider-free):** After the F14/F27 GPT-5.6
whole-request ESCALATE results, the first offline implementation slice
is `odyssey_core/candidate_scoped_handoff.py`. It consumes the frozen
real GPT-6 v3 candidate evidence through the independently validated
`CoreCandidateContext` and creates **one explicit Core-owned work item
per verified safe candidate**, with literal original past-clause text,
source candidate ID, distinct selected roles, grammatical first-person
predicate evidence, original date source span, and narrowly verified
predicate/date inheritance. The unresolved future is recorded
separately as `pending_candidate_ids`, and is absent from all planning
item source/payloads. Thus F14 yields one independent item and F27
yields two separately identified items (sharing the full original
past-clause quote as context, *not* conflating their selected facts).
No text is rewritten into invented grammatical source material.

This is strictly a **read-only preview, not a connected planner**:
`can_auto_execute=False`, and `write_authorized=False` on every
item. No Core provider call, production route, canonical write,
metadata schema change or model switch has occurred. It currently
accepts only the reviewed small two-clause F14/F27 shapes and fails
closed on unsupported structures, cross-clause correction cues,
condition/polarity/replacement, missing future reference/date,
missing original date/subject, or missing order/precisely demonstrated
sequential inheritance. Unit tests replay the saved provider evidence
and tampered variants. Next implementation gate is to connect each
reviewed payload to the **existing** GPT-5.6 Core planner as an
individual planning call, then bind its plan fact to its selected
original source candidate and retain full-source coverage plus
durable pending, before any isolated write can be authorized.
Do not represent this first slice as completion of that runtime
handoff or as successful real-model scoped planning.


**Block 4B28 real GPT-5.6 per-fact planning and physical Core verification
(2026-10-10, experimental branch ONLY):** The model invocation path now
passes independently scoped, Core-owned source-proven facts to the **existing
unchanged `OpenAILunaExperimentalPlanner`**, exactly one source unit per
provider call. `candidate_scoped_handoff.py` retains each original source
quote/role/date/ordinal and an immutable digest of the complete input;
`candidate_scoped_planning.py` creates a Core-owned, grammatically derived
single-fact request (not falsely labeled a verbatim user quote) with ONLY
that fact's already verified original Temporal date. No future unresolved
pronoun appears in any model request. No new specialized planner or app
mutator was created.

All **three actual GPT-5.6 Luna/low live calls now return `PLAN`**:
- F14/candidate-1 -> `Ayer hablé con Eric y Luis.` -> one dated
  `Hablé con [[Eric]] y [[Luis]].` fact (two separate identity helpers).
- F27/candidate-1 -> `Ayer hablé con Eric.` -> one dated Eric fact.
- F27/candidate-2 -> `Ayer hablé después con Luis.` -> one separate
  dated later Luis fact. Core preserved the explicit ordering.

The three exactly reviewed, hashed, source-only model calls (`store=false`,
no retries) produced frozen synthetic model receipts under
`benchmarks/fact_candidate_core_live/results/*--F14--candidate-1.json`,
`*--F27--candidate-1.json` and `*--F27--candidate-2.json`.
Observed 10,603/345, 10,601/257, 10,602/295 input/output tokens,
respectively. At standard pinned rates, all focused live Router/Core
calls together estimated **USD 0.0259652**, under the existing explicit
USD 0.07 ceiling (not an invoice). No further paid calls required here.

**Important cross-unit safety:** Core joins F27's two independently
compiled one-fact `RequestPlan` objects into one ordered canonical
same-Day action by reindexing the second already-verified identity
placeholder and moving the original immutable facts/helpers unchanged.
The original Core-only sequential source coverage now also recognizes
`Hablé después con` as equivalent to `Después hablé con` for the
explicitly supported `y después con` user source shape. Both F14 and
F27 merged plans pass **full original user-source coverage**: one claim
per real candidate, one claim per persisted fact, and a separate pending
ambiguity claim for the missing cinema person. These are real model
responses recompiled through the original Core compiler, not fabricated
or preselected human plans.

Isolated physical Markdown E2E now proves F14=1 and F27=2 distinct
original-day linked facts, physically verified readback, distinct Eric
and Luis canonical references, **durable unresolved `él` pending**, and
safe later `Con Luis` continuation adding ONLY the future cinema with
Luis while retaining the original Day without duplication. All writes
occur in disposable test vaults; **nothing changed in DEV/PROD or any
real notes**.

**Remaining limitations before activation:** This pilot deliberately
only understands the exact reviewed two-clause F14/F27 source pattern,
not arbitrary natural-language splits, conditional negations,
corrections or cross-clause dependencies. The per-fact orchestration
is opt-in and not yet connected to the runtime chat path. The other
23 approved Router design examples and full production-scale semantic
coverage remain untested. Historic unrelated test failures still need
independent release review. Keep Core GPT-5.6 and Router v0 settings
unchanged.


**Block 4B29 reusable reference/dependency diagnostic (2026-10-11,
feature branch and test-only):** The real GPT-6 Router v3 responses for
F08/F13/F23/F26 are already frozen in the PR. Rather than introducing
individual phrase-specific handlers, Core now has
`candidate_dependencies.py`: a **read-only, type-agnostic source-role
dependency trace** that follows only declared source-validated backwards
inheritance, preserves source span + origin unit + explicit vs inherited,
allows an explicit same-role override, and fails closed on missing
inherited evidence. It NEVER decides that a pronoun, "same hour" or
elliptical "other" denotes a concrete value or identity; that work stays
with existing Core semantic planning/identity resolution or Temporal.

Observed: F08's Luis already carries exact original `time` phrase
"a la misma hora" and inherits Marta's *predicate*, not her time;
Temporal must resolve the relational phrase to 10:00. F23's second
Odyssey problem inherits the **project subject** and "tiene"
predicate, but "otro" still requires Core semantic interpretation as
another failure, without fabricating a direct `object` inheritance.
F26 has a real `reference` role "lo" referring potentially to the
original report, but no verified canonical cross-unit object binding;
the trace preserves it unresolved and does not guess a Note ID.

The existing **Core canonical identity handoff** had a genuine general
false negative with the real F13 GPT-6 Router result: its original
reference role "él" is source-grounded but omitted from the event
*anchor* list. Previously Core required every reference role to be
inside an anchor, so actual Router v3 evidence was incorrectly rejected.
Its Core-only preflight now accepts a role proved inside the **single
source clause containing the candidate anchors**, only if no other
candidate anchors compete inside that same clause. It still requires
one predecessor original named identity, an actual currently persisted
canonical identity reference and existing freshness/time-of-use guards;
F14/F27 multi-person ambiguity and unrelated clauses abstain. A
provider-free Markdown integration test confirms real F13 Router input,
persisted canonical Eric proof and guarded future Eric cinema write,
plus negative tests for another-clause role and competing anchors.

The existing `bind_temporal_to_fact_candidates` adapter is already
compatible with independent exact time-value evidence for the real F08
source phrase; no app-owned identity, time inheritance or write logic
was introduced. A single frozen, hash-pinned, unchanged GPT-6 Temporal
model request is prepared in
`benchmarks/fact_candidate_v2_live/run_temporal_reference.py`
to determine whether the actual Temporal model normalizes both
"a las 10" and "a la misma hora" to the same timestamp.
Its request is restricted to synthetic F08, `store=false`,
output cap 512, reasoning low, no retries, with one durable attempt
and original-candidate binding/readback only, **no vault access**.
Approx. USD 0.0008405 conservative maximum plus USD 0.0337352
previous observed focused spend, below the already explicitly
authorized total USD 0.07. Any provider/model failure is evidence, not
reason to silently retry or invent an hour. New offline focused guards
include repeated/unaligned references, wrong source roles and date-only
clock responses.

**Limits:** This is NOT generic production activation or proof that a
model can semantically resolve F23's "otro" or F26's "lo". Next gate:
test independently generated per-unit Core GPT-5.6 plans and source
coverage for those two dependency patterns and explicit ambiguity
before ever granting write authority.


**Block 4B29 supplemental real Temporal F08 result (2026-10-11):**
One approved no-retry original GPT-6 Temporal request, with the
fixed synthetic 2026-10-09 clock, finished successfully (366 input
+ 354 output tokens, `store=false`). Actual response is pinned in
`benchmarks/fact_candidate_v2_live/observed_f08_temporal.json`;
using the unchanged Temporal parser plus original real Router v3
candidate binder, the explicit "a las 10" and the referring
"a la misma hora" both normalize to
`2026-10-10T10:00:00+02:00` on the same resolved day. The result
shows this **one F08 example works with current Temporal**, without
needing special-case phrase handling or new date inheritance.
This is not a claim all relative-hour constructions are proven.

The real F13 Router result had a second concrete mismatch: it
provided the exact source role `reference=él`, but left that role
outside the selected event anchors; Core's original strict
canonical-reference handoff therefore incorrectly abstained. The
updated Core *clause-ownership verifier* can prove a referring role
from the original bounded clause containing the selected candidate's
anchors, with no competing candidate anchors in that clause.
This is a general source-bound safety check, **not** a new sentence
splitter, resolver or a Router instruction. Canonical identity proof,
source/canonical content freshness, uniqueness, original note writes,
and the existing Core dependent write preflight remain unchanged.
Frozen real GPT-6 F13 evidence plus previously persisted Eric
canonical source now succeeds through an entirely isolated
Core guarded future-day write. Cross-clause and competing-anchor
negative tests still reject without writes.

For F23, the generic role-origin trace proves that the second
`property` inherits source `subject=El proyecto Odyssey` and
`predicate=tiene` but its literal object "otro" does not
independently prove the repeated noun "fallo"; it still needs Core
semantic validation, not automatic invented `object` inheritance.
For F26, Core's trace retains `reference=lo` but no authenticated
canonical target for `El informe` has been established. This is
a *type-generic* document coreference gate, not a reason to associate
arbitrary antecedents. No production write, deployment, model
migration, or change to the existing Router v3 prompt occurred.

New live Temporal cost estimated USD **0.0002136** at pinned standard
rates; cumulative all focused GPT-6 Router + GPT-5.6 Core estimated
USD **0.0339488** (not invoice) against prior explicit USD 0.07 cap.
No new Core paid call was made.


**F23/F26 real-model dependent-scoped fact review, 2026-10-11:**
The previous staged GPT-5.6 Luna/low single-candidate provider diagnostic
already completed **all four** real calls under the existing authorized
synthetic budget, and the fourth untouched synthetic JSON is saved in
`benchmarks/fact_candidate_core_live/dependent_results/`. No need
to pay for duplicate calls or new Core instructions. Both original
F23 facts and both F26 facts returned valid `PLAN` from the **unchanged
existing Core planner**, each in a separately selected source-clause
request, with the previous clause supplied only as read-only
linguistic context on dependent second units. The Core model inferred
"otro fallo" from its previous F23 context and "el informe" from
the previous F26 context without a string-replacement rule.

Provider-free tests under
`tests/runtime/test_fact_candidate_dependent_actual_core_vertical.py`
recompile all four REAL Core responses using the production compiler.
Against disposable, isolated Markdown identities: F23 physically
records the Router and Temporal faults on the same canonical Odyssey
project, with Router linking to an existing project Note. F26
physically records receipt of the document on the document and
sending that SAME document to Ana in the current Day, without
duplicates, both with an existing canonical document and with
a newly created typed singular document. Normal target selection
and file write mechanics therefore WORK in these sample conditions.

**Important non-release result:** Both merged actual Core plans
still **fail the original full-source candidate-coverage semantic
veto**. F23 has a shared/inherited Project subject and a source
project-to-component relation that the existing independently-targeted
property validator does not certify. F26's "lo" needs a
source-verified unique antecedent/canonical document association even
though Core produced a plausible exact document reference and the
disposable Markdown writer resolved it. These are not permissions
to broaden source comparison to unrelated phrases or to skip
pre-write coverage. A generic Core-owned identity-and-source
dependency attestation for shared subjects and unique prior
antecedents is the actual remaining gate before any chat/runtime
activation; do not add word-specific F23/F26 exceptions.

Four individual GPT-5.6 real receipts used, respectively,
10,204/247, 10,296/339, 10,598/261, and 10,695/444
provider input/output tokens; cumulative focused Router+Core+Temporal
estimated standard-rate total **USD 0.0438566** (not billed amount),
under the explicit USD 0.07 cumulative test ceiling. No DEV/PROD
activation, real Notes access, credential changes or model switch.


**Block 4B30 — bounded, generic original-source dependency attestation
(2026-10-11, not runtime-enabled):** The reusable
`odyssey_core/candidate_dependency_attestation.py` now checks the
*full original source* against **two independently compiled, saved-real
GPT-5.6 Core plans**. It reuses Core's existing source-validated
candidate dependency/coordination evidence rather than reinterpreting
language in Router or producing another planner.

For **shared-subject properties**, it demands one uniquely original
subject, one explicit inherited subject/predicate origin, both Core
targets selecting the same typed note, independent source-grounded
objects/locations, consistent original predicate and source content,
and a uniquely source-signaled other-instance relation. Changes of
project, component, property noun, or fabricated additional subject
fail closed. It checks both F23's real model output and the previously
unseen Nébula/API/interfaz vocabulary.

For **a preceding typed identity plus anaphoric later fact**, it
demands one explicit original antecedent, one source reference in the
dependent fact, the exact same typed source identity in the first
Core target and the second plan's canonical reference helper, a
separately source-grounded recipient, and distinct correctly ordered
Core temporal anchors. Wrong document, wrong person, wrong target
type/day or unsatisfied references fail closed. It checks F26's
real model output plus the unseen contrato/Marta vocabulary.
The first target may be any singular, non-Day canonical Note type
instead of hardcoding the word "informe". These rules are
source-role/type based, not case-ID special handling; they
deliberately reject unsupported, ambiguous or negated clauses.

Attestations carry a full-source SHA-256 digest, hashes of both Core
plans and the exact original source candidate IDs. The initial
`attest_two_dependent_core_plans` proof **never authorizes a write or
claims canonical reuse**. After the ordinary Core machinery has
already written in a **disposable test vault**, its read-only
`review_persisted_dependency` additionally verifies that the
same exact Core request markers physically exist on the canonical
Notes, that shared-subject facts changed the same stable-ID Note,
or that the second document-anaphora fact contains a wikilink to
the exact physical path whose stable ID was written by the first.
An altered link with the original display text or a forged fact
marker fails; both existing-document reuse and ordinary typed
document creation are exercised. Even a successful postwrite
certificate has `may_write_notes=False`.

**Release gate still open:** Original experimental
`build_candidate_coverage_manifest` deliberately has not
been relaxed. It does not yet consume this new independently
validated dependency certificate; the runtime chat does not
automatically route through the dependent two-fact planner.
A write-capable integration still needs reviewed association of
candidate ordinals, pre-write canonical target freshness,
transactional sequencing of new identities, and postwrite
original-source completeness. Do not use post-write evidence as
a pre-write permission. F19/F20 conditions/corrections are not
authorized by this work. No new provider calls, production prompt
or schema changes, DEV/PROD deployments, or personal-vault access.


**Block 4B31: opt-in global Core candidate coverage for independently
planned dependent facts (2026-10-11, Draft PR only).** Normal
`build_candidate_coverage_manifest` retains its historical strict
behavior and STILL blocks unverified dependent claims. The
**separate opt-in**
`build_dependent_candidate_coverage_manifest` takes the original
user text, real Router source-bound candidates and the TWO existing
unchanged GPT-5.6 Core `RequestPlan` objects. It recomputes Core's
earlier original-source dependency attestation, creates a composite
`RequestPlan` by concatenating the actual two Core actions
**without making or changing any fact, target, date or reference**,
and binds the original source + complete combined plan SHA digests
to explicit one-source-candidate-per-fact coverage claims.

`CoreCandidateCoverageManifest` now has an optional, immutable
`dependency_attestation` with a default of None. When supplied, the
**existing normal application pre-write validator** independently
recomputes the full semantic/source dependency attestation from
**the exact two actions that are about to execute**. It rejects a
missing, stale, forged, already-postwritten or write-authorizing
certificate, reordered candidates, extra actions/facts/claims,
conditional/correction roles, mismatched typed targets, wrong
pronoun referent or any changed Core helper. Only this uniquely
re-attested pair can bypass the older *independent* property/
participant/unknown-pronoun lexical checks that cannot represent
shared subjects or recovered typed antecedents. All ordinary
Core identity resolution/preflights still run. No stored copy of
Router's proposed interpretation is granted selection authority.

**Physical validation with saved real GPT-5.6 model JSON:** Core's
ordinary application was executed using the composite F23 and F26
plans in isolated disposable Markdown vaults, with both existing
and originally missing typed documents. Both request-level actions
succeed and the global candidate-coverage preflight passes.
A new read-only
`review_combined_persisted_dependency` verifies the two **distinct
atomic fact provenance markers**, canonical stable IDs and Core
unit-result helper IDs, exact Markdown linked paths and content,
and the same newly created/reused typed document ID as the
previous unit's written subject. It supports harmless differences
in display-label capitalization, without accepting a changed
wikilink target or a forged fact marker. All certificates continue
to say `may_write_notes=False`; post-write facts NEVER grant
pre-write authority. The original generic
`readback_core_facts` currently abstains on one fact in each pair,
because one canonical link/source revision changes after the
second action and it has no *joint two-action source proof*.
**Do not report its old individual per-reference receipts as 2/2
verified**; use only the separate, exact two-fact atomic-marker
audit for the experimental path until the normal unified receipt
layer is extended and reviewed.

**Remaining release blockers:** The experimental opt-in flow is
still not connected to live Odyssey chat/Router dispatch. The
ordinary Core multi-action writer can already reuse an identity
created by its first action in these isolated tests, but a
mid-request failure cannot be claimed transactionally rolled back;
idempotent/pending recovery and stale-target competition should
be tested before activation. The two shape classes implemented
so far (originally coordinated property subjects, one typed
antecedent with source anaphora) do NOT constitute general
language understanding. F19/F20 conditions/corrections remain
outside this authorization. No DEV/PROD deployment, real Note
writes, model migration, new paid model calls or schema change.


**Block 4B32 — fail-closed dependent-request replay and unified two-fact
delivery review (2026-10-11, experimental Draft PR only).**

The existing Core multi-action writer is append-first and may leave a
valid first fact when a later write fails. A **new read-only root-bound
`candidate_dependency_recovery.py`** scans authoritative original
canonical Markdown atomic-fact markers for the same request ID, with
a 5000-note cap and stable-ID uniqueness checks. It classifies two
expected ordinals as `new`, `partial` (only ordinal 0),
`complete` (ordinals 0 and 1), or `conflict` (duplicate/misordered/
unexpected markers). Corrupt/unavailable source Notes fail closed.
Each state explicitly declares `safe_to_retry_automatically=False`.
On the separately authorized **opt-in dependent** path only, ordinary
`execute_request` now checks for existing original fact markers
after the full original-source candidate coverage proof and BEFORE
any Core write. Any already persisted marker blocks the entire
repeat with `CANDIDATE_COVERAGE_REVIEW_REQUIRED` and zero actions.
All other existing Core requests remain unchanged.

**Injected actual-writer failure E2E:** Replaying the saved real GPT-5.6
F23 or F26 two-action plan in a disposable vault, an injected failure
of the second action leaves precisely the first canonical original
fact. A second invocation with the SAME request ID is blocked before
writing, with the original Markdown unchanged (also blocked after
an entirely completed request). Unexpected orphan ordinal 1 is
reported `conflict`, never automatically resumed. This is **not
rollback** and **not automatic recovery**: a user/operator-approved
resume or authoritative compare-and-swap journal is still needed to
handle interruption before the first marker or a concurrent duplicate
request. Do not simply issue a new request ID to bypass this guard:
the prior partial operation must be reconciled first.

The same `CoreCandidateCoverageReview` response type used by the
original source-candidate coverage API now supports optional
`observed_original_fact_ordinals` and `recovery_state`, defaulted
for backward compatibility. The separate reviewed
`review_dependent_candidate_coverage` route recomputes the exact
original-source/Core plan attestation, scans the complete current
root-bound Markdown and requires the full combined two-action
stable-ID/linked-fact audit before reporting **both** candidates as
physically written and semantically verified. A tampered link,
partial action, conflict or stale source results in BOTH candidates
marked `planned_unverified`, the physically present ordinals
surfaced separately, and
`safe_to_report_all_candidates_complete=False`. It cannot mint
write authority, alter Notes or suppress pending manual recovery.
This differs from the historical one-action readback that
appropriately abstains when the canonical source revision changes
across dependent actions.

**Current status:** Safeguard and reviewed reporting are opt-in
for the paired dependency manifest and NOT connected to chat/DEV/
PROD or public runtime delivery. Core continues using GPT-5.6 and
the original Router v3 prompt unchanged. Synthetic tests replay
the already obtained real GPT-6/GPT-5.6 provider data, without
new billable calls. Remaining release checks: concurrent same-ID
admission/lock or durable intent journal, deterministic and
authorized single-action resume without duplication, lifecycle
of newly created typed identities if a failure precedes a fact
marker, and embedding these verified statuses in user-visible
response after app integration. F19/F20 corrections/conditionals
remain separate unrelated safety work.


**Block 4B33 — root-local durable admission and cross-process concurrency
for dependent two-fact Core operations (2026-10-11, experimental only).**

The current `candidate_dependency_recovery.py` protects one **Core
request ID** using authoritative Markdown ordinal 0/1 markers, but a
transport retry can arrive with a NEW technical request ID. To
address this without guessing that equal message text is a retry,
the new Core-owned opt-in `candidate_dependency_admission.py`
requires a **trusted stable logical operation key supplied by the
outer chat/delivery boundary**, distinct from the generated Core
request ID. The same key MUST be reused across transport retries.
Repeated legitimate messages with identical text but **different**
outer message IDs remain distinct operations.

The implementation reuses Odyssey's existing local Linux
`fcntl.flock` and fsynced atomic JSON state pattern, NOT a new
service, database, graph, app planner or user-vault metadata.
A configured, actor/root-isolated state directory **outside the
canonical Markdown vault** contains only SHA-256 digests of the
logical key, full source, plan and vault root; technical request
ID; and bounded status (`reserved`, `completed`, `partial`,
`unknown`). No original personal conversation text, identity
or Markdown is copied into the state record. One root-wide
advisory lock spans reservation, normal Core's original-source
coverage/identity write path, full two-fact canonical readback
and durable final status. A second thread or *different process*
with the same stable key cannot pass admission, even if it supplies
a different Core request ID. The persisted record is written and
fsynced **before any canonical Note mutation**.

`execute_dependent_core_once` is an **opt-in Core facade** for
already independently compiled, validated GPT-5.6 Core plans.
It mechanically invokes the existing `execute_request` with
the full source, original Core candidate coverage and ordinary
identity materialization. The facade adds only journal admission,
does not call an LLM and never creates a new specialized semantic
planner. It is NOT connected to runtime dispatch/DEV/PROD.

**Frozen-real-model tests in disposable Markdown** confirm:
- Both F23 and F26 finish with one operation and one durable
  `completed` journal, including an existing and a newly
  created typed document.
- A same-logical-message retry with a different Core request ID
  is denied without a new Markdown write.
- Two simultaneous threads running Core F23 produce exactly one
  two-fact canonical write; two independent operating-system
  processes on the same actor root produce exactly one admission.
- A simulated second-action failure leaves one physical fact,
  records `partial` and blocks a new technical ID with the
  same original logical key.
- Process death via `os._exit` immediately after a journal
  reservation leaves durable `reserved` state; restart cannot
  silently retry it, regardless of whether any fact marker exists.
- State path inside the vault, symlinked state/lock, invalid key,
  or journal read/size/capacity failures refuse mutation.
- Two separate, deliberate messages with the same natural-language
  text and different stable operation IDs are NOT conflated.

**Still unproven / never claim ready:** The outer Odyssey chat
must provide and persist a reliable per-message operation ID, and
all relevant cooperating writers must respect the root-bound
admission protocol; direct normal Core calls are not protected by
this new optional facade. A crash after creating a typed Note
but before its first atomic fact may leave an orphan requiring
manual reconciliation. A different logical key passed for an
actual retry is indistinguishable from a new user message
without trusted transport identity and **must not be accepted as
a safe replay mechanism**. No automatic resume/rollback, no
retention/deletion of uncertain journal entries, and no active
runtime wiring are provided yet. F19/F20 correction/conditional
semantics are separate work. All work is on the Draft feature
branch and uses no additional paid provider calls.


**Existing chat-ID contract verified (read-only, 2026-10-11):**
This does **not** require a new browser-generated ID or frontend
payload field. `odyssey_web/client.js:createSubmission()`
already creates one secure `web-<UUID>` per user message;
`requestProductResult()` sends it as `request_id`;
`findRecoverableSubmission()` reconstructs a retry using the
**same original user-turn request ID** instead of generating
another. The runtime's existing HTTP `/execute` accepts that
validated `request_id`, and
`odyssey_runtime/composition.py:execute_product()` already
performs root/actor-bound completed-delivery replay via
`LocalDeliveryResultStore`. Routed subunits derive separate
deterministic `route_execution_id(outer_request_id, ordinal)`
values while preserving the outer delivery ID as the user's
logical request identity.

The proper opt-in integration is therefore to pass the
**existing authenticated outer request ID** as
`logical_operation_key` to the new Core durable admission
facade, and keep any internal subroute execution ID only as
the subordinate Core request ID. The existing actor-isolated
conversation/state root should supply `state_root`; do
not put journal files in the canonical Markdown vault.
Existing completed-delivery replay remains authoritative for
returning a cached successful response; the Core admission
journal additionally protects the **in-progress/crash/partial**
window not covered by a completed response cache.
The current `_execute_lock` serializes one local runtime
instance but is not a substitute for cross-process file locks.

Before switching on this opt-in path, validate the actual
runtime/n8n route owns the same externally supplied request ID
for both original submission and explicit network retry,
including restart recovery and separate user/actor roots.
Client requests with no stable outer request ID must **not**
enter the dependent Core admission path. No normal production
route is changed by this analysis.


**Block 4B34 — private chat delivery preview using existing runtime
composition and stable web request IDs (2026-10-11, Draft PR only).**

A new **unregistered** `odyssey_runtime/dependent_candidate_preview.py`
provides an explicit developer-only
`DependentCandidateChatPreview(runtime, core_executor).execute()`
method. It takes the unchanged original message and the **existing
outer browser `request_id` and `conversation_id`**, resolves the
existing local actor's operational root with
`RuntimeComposition.conversation_root_resolver`, and reuses its
ordinary `_execute_lock` and Core's existing root-isolated vault.
No new HTTP endpoint, route catalog entry, production
configuration, application planner or model/prompt modification has
been registered. Authentication-aware multiuser selection is NOT
advertised; the preview deliberately supports only the existing
local `odyssey-runtime` actor until complete actor-to-vault root
selection is verified. Missing/mislocated operational roots
fail closed.

The privileged test callback calls the previously reviewed
`execute_dependent_core_once` with the outer message ID as
`logical_operation_key` and a distinct internal Core
`request_id` as its physical fact marker. The preview verifies
that Core's returned **subordinate ID** agrees with the
fsynced operation journal, and projects only the external
outer `request_id` to the existing runtime JSON result envelope.
It does not rewrite original Markdown fact request markers or
create independent semantic authority.

A separate actor-root
`LocalDeliveryResultStore(.../dependent-preview-deliveries)`
uses the **existing conversation + original-text SHA-256
fingerprint**. Only the normal Core application result with a
`completed` journal that has passed the two-fact canonical
physical audit can be saved as a completed delivery. After a
simulated runtime restart, the cached result is returned
with `delivery_replayed=true` without rerunning either Core
action or model. The cache verifies the durable operation journal
before replay and rejects a deleted/stale journal, a different
conversation, or the same outer request ID bound to a different
source message. A partial operation cannot enter this cache;
on explicit retry its durable Core admission declines further
writes and the preview returns a typed
`needs_attention` result with zero new actions.

Offline full-stack vertical tests replay original **real saved**
GPT-6 Router/GPT-5.6 Core F23 and F26 data through
`RuntimeComposition`, the existing Core mutation boundary,
isolated Markdown notes, actor-local journal and durable
delivery-result cache. Tests cover one original two-fact success,
both existing and newly created document identity, reboot by
recreating the runtime object, partial second-action failure
and retry, conversation/source ID collisions, forged subordinate
Core result IDs, missing operational state and the absence of
normal HTTP/runtime composition registration. No API provider
calls or real vault mutations occur.

**Outstanding before activation:** This is a privately callable
product-style preview, *not* the HTTP chat endpoint. Its callback
is presently injected only by tests using frozen real model
outputs. The actual deployed n8n/Router → Temporal → independent
Core planner → executor assembly is not switched onto this path;
the frontend cannot invoke this preview, so no changes appear
in the user's running Odyssey chat. Need a separately reviewed
non-default experimental wiring point that maintains trusted
per-actor vault + operational roots; manual reconciliation after
crash, mid-write failure or note-only CREATE with no first marker
continues to block automatic resume. Current original F19/F20
conditional/correction cases are not supported by this
limited dependency path.


**Block 4B35 — source-validated Router → Temporal → existing Core provider pipeline
connected to the *private* chat-delivery preview (2026-10-11).**
The new `odyssey_runtime/dependent_candidate_pipeline.py` assembles the
already present `OpenAIFactCandidateRouter(..., prompt_revision="v3")`
and `OpenAITemporalInterpreter` with independently instantiated
`OpenAILunaExperimentalPlanner` for each bounded source-clause
candidate. The Router adapter is only allowed to return original-text
source roles; the existing Core dependent-scope validator independently
proves safe clause boundaries BEFORE either Core plan call. Temporal
alone resolves original date/time roles from the entire user text,
and missing/approximate or ungrounded date evidence fails closed.
For each Core planner request, only its original literal clause
and a non-operative linguistic quote of the preceding clause are
supplied; the same existing GPT-5.6 Core prompt/schema decides Note
targets, canonical person/document identities, content and task
ownership. There is no miniature planner in Router, Temporal,
Calendar or the runtime adapter.

The private `DependentCandidateChatPreview` envelope can invoke
this pipeline through an explicitly injected callback, and the Core
original-source two-candidate coverage, actor-local operation admission
flock, persisted canonical Markdown and two-ordinal physical audit
remain the sole write authority. A retry that has a completed
delivery cache is replayed from the original root. The preview now
checks a *reserved/partial/unknown* operation journal before the
callback or any model provider is called; the client receives a
typed `needs_attention` without a duplicate or unnecessary model
re-planning. Core keeps its subordinate request ID on atomic fact
markers; the chat response keeps the external browser message ID.

**Vertical evidence uses saved genuine provider outputs:** For F23
and F26 the unchanged **actual SDK-backed Router GPT-6 v3 adapter**
consumes previously captured real provider JSON and the existing
**GPT-5.6 Core model planner** independently reparses the four
actual saved Core JSON outputs. The private runtime calls
`execute_dependent_core_once`, which runs normal Core against
disposable synthetic canonical Notes, checks original-source
coverage and actual same-stable-ID links, and persists an isolated
delivery record. Simulated runtime reboot with the SAME outer
request ID replays the result without another Router, Temporal,
Core model call or Note write. F26's temporal interpretation in
these replay tests uses **synthetic fixed-clock exact date responses**
through the real Temporal adapter, *not a new genuine provider
response* for F26; previously F08's relative time was separately
verified with genuine Temporal. No provider calls or personal
knowledge access are made by this block.

Safety examples F19 correction and F20 conditional are explicitly
rejected BEFORE Core model planning; insufficient/extra Temporal
evidence, mismatched Router original source, Core planner
`ESCALATE`, changed multiuser principal and lost actor-local
roots also abstain. Two separate local-instance state/vault
roots remain independent even when their browser message IDs
happen to match. The private preview is **not registered** in
the normal production/DEV HTTP `/execute`, normal chat
composition, n8n routes or web client. Actor-bound hosted
multiuser vault selection remains unresolved, and the preview
fails closed on authenticated/external principals rather than
silently writing another actor's local vault.

**Remaining activation boundary:** The verified provider-shaped
end-to-end chain is available only through *injected offline
preview callbacks*. No live provider call has tested this exact
full source-to-persistence flow under the user's current model
configuration, and no deployed switch or opt-in HTTP entry
exists. The current reviewed dependency scopes are still
deliberately limited to two unambiguous coordinated facts
with certified shared subject or one typed antecedent, NOT
general all-sentence support. Recovery of partial/crash writes
still needs review, not an automatic retry or rollback.
Keep PR Draft, GPT-5.6 Core, normal chat and real vault unchanged.


**Block 4B35 — actual source-based Router → Temporal → independent Core
pipeline assembled in PRIVATE chat delivery preview (2026-10-11,
Draft PR only).**

`odyssey_runtime/dependent_candidate_pipeline.py` now wraps
**existing actual adapter classes**:
`OpenAIFactCandidateRouter(prompt_revision="v3")` on the exact
original user text, `OpenAITemporalInterpreter` on that SAME full
source only if original candidate source roles actually contain
dates/times, `bind_temporal_to_fact_candidates` for the unchanged
source-offset evidence, `to_core_candidate_context` and
`preview_dependent_clause_scopes` for Core's existing dependent
two-clause source guard, and **TWO** ordinary
`OpenAILunaExperimentalPlanner` instances (Core GPT-5.6 low)
each planning its own original selected clause with prior lexical
context read-only. No Router app plan, no custom temporal resolver,
no alternate Note schema, no new Core semantic planner.
Only source-grounded exact/date typed Temporal facts can be passed
as Core-owned `DomainInterpretation`; unproven/relative/ambiguous
clocks and inherited dates without a separately reviewed clause
scope fail closed. Every present candidate temporal source role
must be verified for **both** units BEFORE any Core model call.
For requests without dates (e.g. F23), Temporal is correctly not
called and no artificial current-day event is introduced.

**Actual existing provider adapters, no new billable calls:**
Tests inject previously frozen **REAL completed** GPT-6 Router v3
and GPT-5.6 Core model response JSON through the adapters'
unchanged SDK interface. F26 Temporal uses a transparently
**synthetic deterministic** date response (2026-10-03
for "ayer" and 2026-10-04 for "hoy") through the existing
Temporal adapter — F26's independent real provider Temporal output
has NOT been evaluated in this block. F23 needs no Temporal.
Tests check true provider-facing model names/low effort and the
same separately source-scoped Core requests as the prior paid
receipts, without calling a live network.

The prepared immutable pair is passed to the previously
reviewed Core `execute_dependent_core_once` and from there to
the NORMAL Core `execute_request` with original-source two-fact
coverage, canonical typed identity resolution, real disposable
Markdown writes, post-write atomic fact provenance/wikilink
readback, actor-root durable operation journal and the separate
preview chat result cache. Simulated runtime restart with same
outer browser message ID returns cached JSON without calling
Router/Temporal/Core again. A partial write leaves the journal
marked `partial` and **is denied BEFORE calling any model
provider** on retry, avoiding both duplicate Notes and
unnecessary LLM cost. A changed original message with saved
candidate source spans, omitted/superfluous temporal mention,
unspecified clock, negative/corrective condition and non-PLAN
Core result never reaches the canonical writer.

**Isolation/security:** The existing private
`DependentCandidateChatPreview` currently supports ONLY
the local `odyssey-runtime` actor. It explicitly rejects a
non-null `AuthenticatedActorContext` or
`ExternalPrincipal`, rather than silently writing another
actor's request into a single local vault; true multiuser
preview requires an actor-bound vault selector. Separate
local instances with independent vault and state roots may
reuse an outer message ID without cross-instance replay.

**Crucial incomplete release boundary:** This is an
*injected, private runtime pilot* and is NOT registered with the
normal public HTTP `/execute` endpoint, frontend chat
dispatcher or n8n production route. Provider replies are
replayed/faked in tests, not live called in this block. The
current code only authorizes the conservative two-clause
dependent semantic shapes demonstrated; it is not yet a
general Router v3 replacement for all 27 cases. F19 and
F20 semantic correction/condition alternatives remain
separate. No DEV/PROD, personal vault, secrets, model migration
or source schema changes.


**2026-10-11 — General Router/Temporal/Core refactor, replacing the misleading two-fact pilot (Draft PR #152, NOT DEPLOYED).**

**Problem discovered:** The preceding experimental path constrained the
user message to exactly two source candidates, one coordinating 'y',
two independently scoped Core plans and one fact per plan. Additional
validators recognized particular word patterns such as 'otro',
'lo', 'hablé con' or 'él' and were extended with admission journals
and private runtime preview infrastructure before proving a general
linguistic contract. Passing those experimental tests had been
incorrectly described as readiness of the general architecture.

**Architectural decision:** The existing ordinary Core planner already
accepts the unchanged **whole source**, the entire validated variable
Router candidate context, optional Temporal DomainInterpretation,
and emits a normal RequestPlan containing zero/multiple actions and
zero/multiple facts per action. Return to THAT path rather than
another split-and-plan-per-candidate coordinator. Router describes
source spans/roles/dependencies, Temporal independently interprets
the original whole message, Core alone decides semantics and writes.
No model/prompt/schema changes.

**Actual reversible feature-branch changes:** The two-candidate
runtime preview/pipeline, its Core dependent-pair attestation,
recovery and admission modules, and its custom source coverage
exception were removed; ordinary Core's original prewrite
coverage gate remains unchanged and fail-closed. Original frozen
GPT-6/GPT-5.6 receipts remain untouched. Historical two-candidate
test-harness scoping was moved out of `odyssey_core/` into
`benchmarks/fact_candidate_core_live/legacy_dependent_scope.py`
and the meaningful offline source and real-model frozen tests
were retained as benchmarks. Tests solely exercising removed
private infrastructure were retired, not silently counted as
regressions or evidence of general language capability.

New **read-only**, cardinality-independent
`odyssey_runtime/complete_source_handoff.py` calls the original
Router adapter once on the whole message, uses the already existing
Core source-role and backward-inheritance validator on all N
candidates, optionally calls the original independent Temporal
adapter on the whole source **even when Router did not propose a
temporal role**, validates precise source/time provenance, and
passes the full source and all evidence to the existing Core
planner **ONCE**. It does not produce a Core RequestPlan itself,
infer identity, set Note types, split actions or authorize writes.

Focused tests cover 1/2/3/5/8/13/26 candidates, transitive
inherited roles, repeated/ambiguous pronouns, full-message dates,
missing/mismatched Temporal role evidence and arbitrary Core
action counts. A separate actual-Core-write vertical uses 1,
3, 5, 8 and 13 independently provided original source facts,
one normal WriteAction and one canonical synthetic Day note,
with the existing Core original-source coverage check and actual
Markdown fact-marker readback. In that physical test the Core
plan is synthetic, not a newly observed GPT-5.6 completion, and
the existing coverage result itself continues to say
`candidate_semantics_verified=False`.

**Crucial release blocker:** The existing opt-in general
`candidate_coverage.py` still assumes one explicitly attributed
fact ordinal per Router candidate and contains prior narrow
lexical/person/relation validators. It is NOT sufficient to
certify all real sentences, paraphrases, one-to-many or many-to-one
source-to-fact associations, correction/condition semantics and
multiple subjects/pronouns. The new handoff is therefore
READ-ONLY and NOT connected to ordinary Core mutation or to
the deployed chat. The next justified work is Core-owned
semantic completeness/attribution for *variable candidate and
fact cardinality* while preserving its existing identity and
source validation, followed by live GPT-5.6 evidence and
safe per-user runtime dispatch. Do not reintroduce a
two-candidate special-case bypass or equate a mechanical write
with semantically verified capture.

No new paid provider calls, model switch, permissions, security
boundary changes, runtime chat activation, DEV/PROD deployment
or modification of the user's canonical vault.


**2026-10-11 — first complete offline execution gate using the EXISTING
Router → independent Temporal → Core Planner → Core preflight/identity → Writer.**

Phase contract: connect the current full-source candidate/Temporal handoff
to ordinary `odyssey_core.application.execute_request`, never one Core
plan per Router candidate or one note per candidate. Acceptance is a
single source-preserving Router and Temporal pass, a single genuine
Core SDK planner/semantic compiler pass, the existing mandatory
original-source coverage preflight and real canonical Markdown
Writer/readback on disposable, root-bound notes for variable source
unit/fact counts; refuse unsafe or missing Core review *before* writing.
Out of scope: new semantic attribution models/prompts, new app
planner, hosted actor routing, automatic partial-work recovery,
DEV/PROD deployment or a new HTTP endpoint. Architecture challenge:
**PROCEED** using the already existing `execute_request` and
`CoreCandidateCoverageManifest` checks; creating another executor
or relaxing coverage would repeat the former architecture mistake.

`odyssey_runtime/complete_source_handoff.py` now also exposes
`execute_complete_source_with_core(evidence, core_planner_factory,
candidate_coverage_factory, ...)`. It calls **exactly the existing
`execute_request`** with one unchanged whole-source
`OpenAILunaExperimentalPlanner` (GPT-5.6) and
`candidate_context`/independent review callback. There is no
separate Writer, target resolver, mutation loop, compound
RequestPlan builder, inferred Core fact ordinal, special vocabulary,
case ID or per-unit Core model call. The callable remains
**explicitly non-default**, unregistered in the installed runtime
server/product dispatcher.

Full-stack deterministic tests in
`tests/runtime/test_complete_source_execution_e2e.py` use
provider-shaped Router, Temporal and Core replies through their
real unchanged SDK parsers. For **1, 2, 3, 5, 8 and 13** source
candidates, Core's actual semantic JSON compiler emits one
`WriteAction` with that many atomic facts; Core validates a
**test fixture's** separately reviewed full-source coverage and
the actual Writer saves N individually marked facts in ONE
synthetic canonical Day Markdown note. The physical source request
IDs/ordinals are re-read using the ordinary Core readback, not
assumed from planner success. Exactly ONE call to each model-shaped
adapter is observed. No real model is billed.

Negative tests require an independent review factory; a missing
review raises before calling the Core provider, and incomplete
claims cause existing `CANDIDATE_COVERAGE_REVIEW_REQUIRED` with
**zero** writes. One source candidate trying to claim three planned
facts remains safely blocked under the existing old
one-to-one coverage restriction; that is a **known semantic review
gap**, not support for one-to-many attribution.

A separate real SDK-to-Core write regression uses ordinary
canonical identities for Eric/Luis, compiles the
previously frozen provider-shaped multi-person utterance into
one Day fact containing both real Markdown identity links,
and retains the subsequent ambiguous `él` candidate
as pending/partial rather than writing the wrong person's
future action. This is a test regression, not a code branch for
names, pronouns or number of speakers.

**Evidence boundaries / remaining work:** Core semantic outputs
used for this gate are deterministic **synthetic provider replies**.
The materialization, date/identity/coverage validators and
Markdown readback are real, but this does not establish the
current live GPT-5.6 model's accuracy on arbitrary messages.
The independent coverage callback in tests is a manually
checked fixture mapping and MUST NOT be generated mechanically
from Router candidate order in production. Broader N↔M semantic
Core review, per-user root-authenticated runtime integration,
live original-source model evidence and genuine crash/partial
state reconciliation are still required before DEV. No
production route, provider model, canonical schema, user
vault or live n8n workflow was modified.


**2026-10-11 — Core N:M candidate/fact verification and replay of saved real provider responses (no live credentials available).**

Architecture checkpoint: **PROCEED with existing Core read-only attribution module.** A Router candidate is neither a fact nor a Note. Source completeness may require 1→N, N→1 or N↔M candidate-to-fact links. The legacy execution coverage manifest and old model-facing attributor still accept only one ordinal per candidate. Do NOT loosen their write authority, infer identities or add a second Planner.

Added `CandidateFactLinks`, `CandidateFactGraph`, and `inspect_candidate_fact_graph` **inside existing `odyssey_core/candidate_attribution.py`**. This is a typed, non-executing Core diagnostic, not a new app or provider model contract. It validates original immutable source and plan digests, candidate order, exact original source-quote anchors, sorted/unique/bounded Core atomic ordinal edges, complete source-candidate accounting, complete planned-fact coverage, explicit pending status and refusal to treat unresolved/conditional/negative scopes as proven. One source candidate may have multiple fact ordinals and multiple source candidates may propose the same ordinal. The result explicitly has `semantically_verified=False`, `may_authorize_writes=False`. No test bypasses normal Core identity, phrase, polarity or mutation guards. Passing structural N:M review is **NOT proof of semantic equivalence**.

Tests cover 1:1, 1:3, 3:1, 3:5, 5:3, 8:13, 13:8 and 26:26, stale plan fingerprints, missing candidates/facts, forged/duplicate/unordered/boolean ordinals, tampered source anchors, correctly pending ambiguous identities. An isolated Core execution test explicitly supplies that graph as a candidate coverage callback and verifies existing Core refuses it with `CANDIDATE_COVERAGE_REVIEW_REQUIRED` and **zero Markdown writes**: there is no privilege escalation from model suggestions to persistence.

Because current remote development session has **no `OPENAI_API_KEY` environment credential**, **no new live GPT-6/GPT-5.6 calls** were attempted. Do not load credentials from unrelated servers or log secrets. Instead new benchmark regression tests reconsume **authentic saved prior GPT-6 Router v3 responses for all 27 approved design examples** via the production-capable SDK adapter. All 27 original source proposals validate; **26 of 27 dependency traces pass**. The remaining real-source proposal is F27: candidate 2 inherits `subject` from candidate 1 even though no explicit subject source role exists there (implicit first person in verb). Core correctly raises `CandidateDependencyError` rather than inventing subject evidence. This is an **open Router source provenance defect**, not an 'only two facts' issue. It must be fixed by a general implicit/explicit subject provenance contract, not a name/phrase/F27 branch or silent assumed self.

The saved **real GPT-6 Temporal F08 result** validates through the current full-source Temporal adapter and source bindings. Two full original **real GPT-5.6 Core** previously recorded plans (F09, F10) decode successfully with the current original-source Router candidate context using exactly one ordinary Core planning call each; F09 includes two facts, F10 one. These receipts are model observations from the previous authorized runs, not fresh live checks or full 27-case real Core semantics. These saved model outputs are not written to private or synthetic notes in this benchmark. Synthetic E2E writes from the preceding stage remain covered by separate tests.

**Still blocked for DEV:** N:M candidate/fact *semantic equivalence* verification (not just graph shape), old Core execution coverage gate's 1:1 assumption, missing explicit-source inherited roles, modern live GPT-6/GPT-5.6 calls when authorized credentials become available, and trusted actor-bound end-to-end runtime/n8n routing. Do not overstate structurally tested graph as authorized general write coverage; do not migrate GPT-5.6 Core to GPT-6. No schema, model prompt, HTTP route, n8n workflow, real vault or DEV/PROD changes.


**2026-10-11 — Generic Core candidate↔fact graph validation (not a semantic-certification bypass).**

The existing `odyssey_core/candidate_coverage.py` now accepts an
**explicit independently reviewed edge set** through optional typed
`CoreCandidateCoverageClaim.fact_ordinals: tuple[int, ...]`.
This is the SAME existing Core prewrite coverage gate and the SAME
canonical Markdown writer/readback, not a new planner/attributor,
router mode or application. Legacy `fact_ordinal` one-to-one
claims retain their exact prior contract, including duplicate
rejection. In graph mode every source candidate must be accounted
for, and every ordinary Core atomic fact must be explicitly
covered, even when several candidates jointly support one fact
or one source candidate expands into several facts. The edges
are supplied by an **independent Core review callback**; neither
Router order nor the adapter infers them. Strictly typed,
source-bound, plan-digest-bound, nonempty and internally unique
ordinal sets are mandatory; invented, omitted, lexically
unsupported, reordered, negation-altered and conditional claims
fail closed before mutation. True ambiguous source referents
remain pending. Canonical links with shared/expanded source
coverage remain blocked until **independently reviewed typed
identity provenance** exists; lexical evidence must not be
promoted to a canonical identity.

Core's existing postwrite `review_candidate_coverage` now
checks **every** physical fact ordinal associated with each
source candidate, so a missing/corrupted one cannot result in
that candidate being marked physically complete. It records
the explicit list of graph ordinals without changing prior
one-ordinal callers. Physical proofs, even when complete, keep
`candidate_semantics_verified=False` and
`safe_to_report_all_candidates_complete=False`. Thus this
change solves a structural one-to-many/many-to-one contract
restriction, but does **not** prove an arbitrary fact really
matches a source interpretation.

N↔M vertical offline tests drive existing Router and Temporal
SDK adapters, the unchanged GPT-5.6 model-shaped Core JSON
semantic compiler, Core prewrite validator, original Core Writer
and actual synthetic Markdown fact-marker readback. Generated
1→N, N→1 and mixed N↔M mappings vary sizes 2/3/5/8/13 and
verify genuine physical persistence. Unjustified swapped edges,
duplicates, invented ordinals, unclaimed facts, explicit
negation/conditional scopes, attempted ambiguous-pronoun
attribution and forged/missing physical markers are rejected
or reported pending. No synthetic mapping is auto-generated
in runtime; only independently reviewed TEST fixtures supply
the correspondence.

**Remaining validation gates:** The automatic Core semantic
reviewer (`candidate_attribution.py`) is still a *read-only
one-to-one proposer*; it does not yet establish N↔M semantic
equivalence nor canonical reference attestation. The recovered
historical actual GPT-5.6 **whole-source** F14/F27 replies
were `ESCALATE`, whereas prior successful saved GPT-5.6
Core fact outputs were for separately scoped candidate inputs;
these are not interchangeable with a new current
whole-message live-model check. No new billable provider calls
or production activation have occurred. Real-provider accuracy
and safe independent semantic N↔M evidence are still open.
