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
