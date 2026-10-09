# Router fact-candidate units v1 — design contract (not active)

Status: **BLOCK 1 / PROPOSED SEMANTIC CONTRACT — awaiting human design review.** No prompt, runtime, note schema, provider call, deployment, or canonical data change is authorized by this document. Historical Router v0 behavior and its frozen evidence are unchanged.

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

Block 3: graph shows candidate IDs and source-bound `explicit`, `inherited`, `overridden`, `unresolved`, `verified` role states per step. Read-only, honest legacy fallback, pagination/mobile scrolling, no fabricated stage outputs. Only validated diagnostic data may cross n8n/browser/conversation allowlists.

Block 4: implement + version the candidate segmentation/dispatch with a contract adapter; keep protected v0/Temporal/Core guards and test rollback in isolated DEV. No production or real-vault deployment until separate authorization.

## Open decisions before implementation (do not silently settle)

1. **Multi-unit outcomes — USER APPROVED:** persist validated independent facts even if another candidate remains ambiguous; block/defer the ambiguous/dependent fact and seek targeted clarification, as in existing clarification UX. Any interdependent candidate with uncertain grounding stays fail-closed. This is product direction, **not yet implemented**; exact concurrency/replay/write preflight remains an implementation proof obligation.
2. **Future plans and negative/conditional assertions:** which of F17/F19/F20 are persistable facts versus proposals/intentions needing confirmation, or task/event lifecycle ownership? Candidate splitting can be agreed without deciding storage semantics. Recommend leaving final assertion/target choice to Core and capability policy rather than Router.
3. **Source anchor representation:** exact substring + occurrence discriminator resolved locally, or a provider-generated offset rejected unless independently checked? Unicode/duplicate wording and backward/forward scopes require a reliable, small closed contract. Recommend provider emits literal source evidence plus disambiguation, local validator calculates offsets; defer exact schema choice to block 4.
4. **Retention/size for diagnostics:** choose checkpoint retention, failure recovery and unit caps in blocks 2–3, without weakening validated stage/flow budgets or creating a new authority.

**Next gate:** human review of the above open decisions and fixture, then explicit approval before implementation; do not merge/designate the v1 behavior active based on design-only checks.
