# Router → route-local Temporal/Core dispatch and dependency handoff

Status: **restored user-approved architecture contract, 2026-10-11**.
This is architectural guidance, **not** a claim that the inactive fact-candidate
prototype is correctly connected or that the active DEV route is changed.
The older per-route behavior remains in `odyssey_apps/router.py`,
`odyssey_runtime/routing.py`, and
`docs/architecture/router-dependent-route-continuity.md`.

## Authority: who receives which text?

- Router alone receives the complete CURRENT user message for segmentation.
  It assigns each route its exact source span, capability, and proven backward
  dependencies. It cannot query Notes, name a canonical identity, resolve a
  date, decide fact ownership, or authorize writes.
- Temporal receives the selected **route-local temporal-bearing source** and
  any bounded inherited source/date context that is actually needed. A route
  with no temporal work does not invoke Temporal. Resolve dates once where
  possible; preserve shared dates, approximate times and ordered temporal
  scopes as typed evidence, not guessed exact instants.
- Core's ordinary Planner receives each selected **route-local source/work
  unit**, its scoped original-source evidence and the relevant verified
  Temporal/canonical dependency carriers; NOT the complete collection of
  sibling routes as another natural-language planning request. Core owns
  identity/Note selection, references, facts, actions and Writer validation.
- For an independently executable route, don't wait for unrelated failures.
  For a dependent route, execute predecessors once and in order, then obtain
  their *actual authoritative Core result*. If a source-visible reference such
  as `él` has precisely one fresh, saved, canonical antecedent, pass a
  Core-owned typed reference carrier to that route; otherwise block that
  dependent write, with visible pending/clarification as appropriate.
- Keep the complete original source as immutable **read-only provenance**
  for exact span checks, source coverage, correction/negation scope,
  unique-mention checks and auditing. Do not pass it to downstream model
  planning as the current request. Provenance checking and model input are
  different interfaces.

## Recovered executable v0 Router contract

The current implementation actually defines
`RoutePlan(outcome, routes)` and each
`Route(capability_id, source_text, depends_on, dependent_mention)`.
The closed provider schema includes the latter two nullable fields.
`depends_on` is a zero-based earlier route index, not a person ID.
`dependent_mention` must be a verbatim substring of that successor.
The router must preserve exact original spans in order and cover the entire
source other than inter-route whitespace; it cannot invent omitted words.

For example, this is a **conceptual illustration of the existing JSON
field contract**, not a claim about an observed provider response:

```json
{
  "outcome": "ROUTE",
  "routes": [
    {"capability_id": "temporal",
     "source_text": "Ayer hablé con Eric.",
     "depends_on": null, "dependent_mention": null},
    {"capability_id": "temporal",
     "source_text": "Mañana iré al cine con él.",
     "depends_on": 0, "dependent_mention": "él"},
    {"capability_id": "temporal",
     "source_text": "Hoy compré pan.",
     "depends_on": null, "dependent_mention": null}
  ]
}
```

Workflow: route 1 → Temporal resolves `Ayer` on that route only →
Core resolves Eric, persists the validated source fact and emits a guarded
`CanonicalReferenceEvidence`. Route 2 waits, rechecks the carrier against
current authoritative Markdown and passes the carrier for `él` to its own
Temporal/Core path. Route 3 is independent and can proceed regardless of a
blocked route 2. No earlier sibling text or guessed `Eric` is fed to Core
as part of route 2. The typed internal `DependentRouteHandoff` has
`mention` and `evidence` fields. The actual guard and proof rules live
in `odyssey_core/application.py` and `odyssey_runtime/routing.py`.
The routing design was proved with an isolated provider-free example under
`tests/runtime/test_temporal_user_path_e2e.py`.

## Richer v1 fact candidate contract: NOT a replacement for routing

The inactive fact-unit proposal from `odyssey_apps/fact_candidates.py`
has a DIFFERENT shape:

```json
{
  "version": 1,
  "units": [
    {
      "kind": "occurrence",
      "anchors": [{"text": "hablé con Eric", "occurrence": 0}],
      "scoped_source": [
        {"role": "date", "anchor": {"text": "Ayer", "occurrence": 0}},
        {"role": "participants", "anchor": {"text": "Eric", "occurrence": 0}}
      ],
      "inheritance": [],
      "state": "candidate"
    }
  ]
}
```

The example is **schematic** and assumes the original source is
`Ayer hablé con Eric.`; every anchor must match those exact original
characters/case in a real provider output, and the validator calculates
positions, not the provider.
`SourceInheritance(role, from_unit)` is 1-based previous-candidate
**lexical/source-scope provenance**, not an execution dependency and not
an identity. A single date/predicate may support multiple candidate
propositions, or several candidate propositions may lead to one Core
fact. Therefore do NOT force these richer candidates into independent,
disjoint v0 `Route.source_text` slices when doing so drops a shared
predicate, pronoun, correction, date or other required source scope.
Instead use a typed **scoped work-unit carrier** with original anchors,
shared/inherited roles and validated dependency edges. It must still send
only that selected work unit (and needed provenance), never all sibling
content as the Core planning request.

Execution-order dependencies are a separate layer, materialized only
after Core has actually produced authoritative predecessor evidence.
A lexical `inheritance` edge is NOT permission to substitute that
predecessor's identity or to write.

## Negative/edge-case acceptance examples

1. `Marta vive en Lyon. Luis vive en París.` → two independent Core routes.
2. `Marta y Luis viven en Lyon.` → two possible independently managed
   residence assertions sharing the original predicate; represent shared
   grammatical evidence or group the route. Do not fabricate
   `Marta vive ...` as a supposedly verbatim original fragment.
3. `Hoy vi a Ana y compré pan.` → independent semantic assertions may
   share `Hoy` and an implicit subject. Pass only verified scoped context
   to each work item, preserving exact source evidence and execution order;
   do not discard an omitted subject or invent one.
4. `Ayer hablé con Eric y Luis. Mañana iré al cine con él.` → the second
   route has a backward reference but the earlier route doesn't uniquely
   identify `él`. Block/defer the second, never select one name.
5. `El proyecto Odyssey tiene un fallo en Router y otro en Temporal.` →
   no time-bearing route; skip Temporal. `Temporal` here is a component
   name, not a date.
6. `Mañana a las 10 iré al médico y a las 12 al cine.` → retain the
   first date as shared context for the second time; Temporal may resolve
   each scoped date/time without incorrectly assigning a new calendar
   date to the successor. Core then handles fact destinations.

## Historical experimental deviation and recovery gate

The feature-branch-only `odyssey_runtime/complete_source_handoff.py`
currently uses `temporal.interpret(source)` and
`planner.plan(evidence.source)`. Both forward the entire current message
to a downstream model; **they violate this contract** and were the
pipeline behind the 2026-10-11 27-case live experiment. Its captured
model responses, physical write smoke and regression corpus remain useful
evidence, but DO NOT copy that adapter as the recommended architecture.
Do not fix the mismatch by pushing additional natural-language text to
Core; the repair is to implement route-local dispatch and **typed**
dependency/result handoffs through the already existing execution
boundaries.

Keep the GPT-6 Router and GPT-5.6 Core versions unchanged during
this architecture repair. Before any DEV activation, run isolated
multi-route end-to-end tests that assert **the exact per-component
input source**, dependence on Core-verifiable previous results, success
of independent later routes after a dependent branch is blocked,
completeness of candidate source coverage, and physical canonical
Markdown readback. Keep the original 27-case corpus and associated
synthetic Notes; do not change case-specific product logic to make
the tests pass.


## Scoped execution implementation checkpoint (2026-10-11)

The opt-in **test-only** adapter
`odyssey_runtime/candidate_route_dispatch.py` now compiles the existing
validated Router v1 proposal into a `RoutePlan` whose routes carry ONLY
their own original `source_text`. It reuses the old and already tested
`odyssey_runtime.routing.execute_routed_request` sequential guarded
executor. The real model's complete source is supplied to Router ONCE;
only route-local source goes to Temporal and the ordinary GPT-5.6 Core
Planner/reviewer. Core handles canonical name/Note identity resolution and
writes; readback proves physical Markdown. Source candidates that share a
predicate/date or lexical inheritance are grouped conservatively, rather
than fabricated as independent original source strings. A later
unverifiable inheritance (historical F27) still fails closed.

For explicit successor pronouns, the executor waits for the predecessor,
checks its real Core-persisted `CanonicalReferenceEvidence` and passes
`DependentReferenceGuard` and bounded canonical Domain evidence to the
successor only. Router's preliminary `ambiguous_identity` source hint
can become eligible for review ONLY for the exact referring candidate
whose unique identity was actually proven by the previous Core result,
after freshness checks; never via Router guessing. Independent Core
candidate-coverage still reviews that successor, and the actual Core
write preflight checks the identity/guards again before mutation.
A forged/stale carrier does not lift ambiguity.

The Core planner and its independent reviewer now each consume the same
bounded, typed predecessor evidence when present, while maintaining
independent model calls and unchanged GPT-5.6 model selection. The
reviewer does not inherit authority from the Core planner. This is an
explicit opt-in model-prompt/contract change only for dependent routes;
ordinary stand-alone prompt content remains as previously rendered.

**Verification:**

- Permanent synthetic canonical Notes: same 13-note disposable vault fixture
  from `tests/fixtures/full_message_corpus_v1/`.
- All 27 frozen prior GPT-6 Router v3 proposals compile through the new
  route generator except F27, which correctly remains blocked for
  unsatisfied inherited-role provenance.
- No-date F09/F10/F16/F23/F25 go directly to Core, no Temporal call.
- Generic Eric three-route fixture executes route 1 then verified
  route 2, plus independent route 3. Three physical Day fact readbacks
  verified. A deliberately misdirected dependent canonical target
  blocks only that route, leaving independent facts written.
- F09 **fresh real models**, 2026-10-11: one grouped, original source
  `Marta y Luis viven en Lyon.`; one GPT-6 Router call and two
  GPT-5.6 Core planner/reviewer calls; **no Temporal invocation**;
  Core updated the two existing synthetic person Notes, status COMPLETED.
- F13 **fresh real models**: all three scoped Router routes were
  exercised with GPT-6 Temporal and GPT-5.6 Core/review when needed.
  The first and third routes wrote physically verified Day facts.
  The dependent second route remained needs_attention across three
  original paid attempts for three distinct provider-contract issues.
  Its last original live result is **PARTIAL**, not a real-provider full
  completion claim. Preserve every attempt in private one-shot receipts.
- Frozen authentic F09-v2 and F13-v3 model-output sequences now live
  (synthetic data only) under
  `benchmarks/application_router/scoped_routing_v1/`. The deterministic
  regression `tests/runtime/test_scoped_route_recorded_real_replay.py`
  replays each real output through the updated adapter and verifies
  **F13's three Markdown facts**, including Eric's canonical dependent
  link, with **zero additional paid provider calls**. A forged/stale
  carrier test proves the model cannot override Router ambiguity alone.
  This is a meaningful corrected offline E2E proof, NOT a freshly
  billed live-model pass after the final identity-state fix.
- Latest cumulative estimated API spend **USD 0.1399806** of the user
  approved USD 0.25; no DEV, PROD, real personal notes, merge or
  production model switch. No later retry was performed after identifying
  the Router ambiguity-state inheritance mismatch.

Remaining: more live scoped-language acceptance cases beyond F09/F13,
including F27's broken predecessor role, conditional/negated candidates,
shared tense and approximate dates. The experimental route-local adapter
still is not wired into the interactive chat's active DEV path; do not
describe its isolated success as a production deployment or complete
acceptance of all 27 cases. Do not reactivate full-source Temporal/Core
handoff to fix those cases. Before DEV promotion, review and test this
opt-in route adapter with actor isolation, durable replay/pending semantics
and model-quality gate for the changed dependent-prompt contract.


## Per-candidate source routing correction (2026-10-11, subsequent checkpoint)

The historical 25-case live matrix revealed that the opt-in
`candidate_route_dispatch.py` compiler was grouping unrelated assertions
whenever they reused a subject, predicate or date. This was a violation of
the above contract, even though all predecessor canonical identity guards
worked in the initial Eric experiment.

The compiler has now been replaced by
`odyssey_runtime/source_scope_compiler.py`. The corrected compiler:

- Segments Router's actual **primary original-source candidate anchors**
  into independently routed clauses, preserving an exact, ordered partition
  of the original message; no insertion, deletion or duplication of source
  characters occurs.
- Validates every shared or inherited grammatical role on the original
  message **by exact character offsets and an immutable SHA-256**, and
  carries the bounded `CoreSourceRoleProvenance` object *outside* the
  next Core fragment as untrusted read-only provenance. The local Planner's
  request remains just its own literal route source. Nothing in this
  provenance is a canonical identity, resolved date, or permission to write.
- Preserves grouping only for a genuinely joint predicate/property event,
  a coordinated purchase with one buyer and several objects, or a correction
  that must not persist its retracted alternative first. Distinct buyers
  and otherwise independent facts do not silently merge.
- Examples with the previously captured, real GPT-6 Router outputs:
  - F06: `Hoy vi a Ana` → ` y compré pan.`, with the second route
    carrying typed **unresolved** source date evidence `Hoy`.
  - F23: `El proyecto Odyssey tiene un fallo en Router` →
    ` y otro en Temporal.`, with typed inherited lexical subject/predicate.
  - F22: now three distinct scoped task routes.
  - F25: now two independent routes; the repeated `La casa de Toulouse`
    source anchor remains proven context, never fabricated in route 2.
  - F16: `Ana compró entradas para el concierto` →
    ` y Luis también.`: two purchasers, not one combined purchase.
  - F19: correction/replacement remains *one guarded atomic interpretation*;
    it must not write the subsequently retracted first plan.
  - F09/F11: compatible true joint-property / one-buyer transaction groups
    may remain atomic. F27 still fails closed for missing lexical provenance.
- Exact downstream dispatch and group counts are asserted for every
  original frozen Router proposal by
  `tests/runtime/test_source_scope_compiler.py`; source corruption,
  external-role offset mismatch and unwanted writes are explicitly rejected.

**Critical open work before DEV:** external `date` provenance does **not**
yet constitute an exact resolved and Core-authorized Temporal anchor.
For F06's second route, Core sees that `Hoy` originated in the earlier
fragment, but the system must NOT manufacture an ISO date from that
untrusted hint. Implement a safe typed transfer of the earlier Temporal
result, with exact role scope and freshness, into the subsequent Core
Planner/Writer contract before claiming that both F06 facts can be
persisted on the same Day. Likewise, inherited canonical subjects and
shared predicates must be audited by Core against actual Notes and not
treated as guaranteed identities.

**Regression distinction:** All 25 previous real Core responses were
generated against the *historical merged model inputs*. For faithful
provider-free comparison, their existing replay tests use a frozen copy
of that original compiler in
`tests/runtime/_historical_candidate_route_compiler.py`, **test-only**.
Product routing uses only the corrected compiler. Replaying an old
whole-source Core response as though it were generated for a new split
source would falsify the regression result. A newly generated live-model
matrix is needed after the typed Temporal/result carriers are complete,
within separately checked API spend. No part of this checkpoint changes
the current GPT-5.6 Core model, DEV, PROD, production Notes or n8n.


## Completed Temporal-to-Temporal and Temporal-to-Core carrier (2026-10-11)

The missing typed inherited Temporal-result transfer is now implemented in
`odyssey_runtime/scoped_temporal_handoff.py` and
`odyssey_core/domain_interpretation.py`. It is an **opt-in experimental
branch-only interface**, not a production workflow switch.

1. Router's scoped source role only states that a later fragment inherited
   wording such as `Hoy` from an earlier original span. That statement
   has no date-normalization authority.
2. Temporal runs against the first local source and returns its verified
   `TemporalInterpretation`. The route executor records only exact
   DATE/DATETIME results keyed by the original, immutable source offsets.
3. A later route can obtain `InheritedTemporalReference` only if its
   `CoreSourceRoleProvenance` matches that exact earlier Temporal span,
   the original SHA-256 source, the expected original words, and a strictly
   earlier execution route. A role with no such proof **fails before
   Core planning or mutation**; none is manufactured from Router wording.
4. If the later route has no new temporal expression, Core's ordinary
   Planner receives only its own source plus that typed inherited date
   as a separate `DomainInterpretation.inherited_temporal` entry.
   Existing Core temporal target/anchor validation consumes that trusted
   coordinate without treating old sibling text as the current request.
5. If a later route also contains a new clock expression, Temporal receives
   its own local user source and a separate bounded typed inherited carrier.
   The Temporal response must still contain only original words from that
   local source. Any new exact datetime conflicting with a single inherited
   exact date is rejected before Core. Unqualified time is **not** silently
   assumed to mean today's date.
6. Core/Writer/physical Markdown readback continue to be the only write
   authority. Canonical identity handoff remains separate.

**New deterministic acceptance examples:** F06
`Hoy vi a Ana y compré pan.` routes as two separate requests; Temporal
is called once for `Hoy vi a Ana`, and both Core writes can finish on
the correct real synthetic calendar day. If the first Core operation is
non-executable but Temporal completed, the second independent fact can
still use the verified date. If Temporal fails, the second fact cannot
write using Router's lexical `Hoy`. F04
`Mañana iremos al parque a las 12 y luego a las 18 iremos al cine.`
routes twice, with the second Temporal call receiving the exact
`Mañana → YYYY-MM-DD` typed first-route proof to resolve its own
`a las 18` into a datetime. A model returning an incompatible day is
rejected. Tests additionally guard offset/digest tampering, future-route
references, fake untyped domain evidence, and prompt source boundaries.

A separate real-model finding: five prior 27-case responses were truncated
at Temporal's 512-token output ceiling. The **historical default remains
512**; only the opt-in scoped provider runner uses a validated upper bound
of **1536 tokens**, preserving existing benchmark budget/contract invariants.
This does not change model choice, inference authority or retry policy. It
reduces but cannot guarantee elimination of provider truncation.

**Still not proven:** Every F01–F27 behavior as a freshly generated
split-input four-model result. Previous saved Core outputs belong to
the historical merged-input contract; never represent their replay as
new split-input responses. Conditional/polarity, tasks, source-inherited
canonical *subjects* and non-exact/duration time formats still need
independent acceptance tests and the general Core graph reviewer gate.
No DEV/PROD deployment or personal-vault access is authorized by this
checkpoint.


## Fresh real-model split-input acceptance (2026-10-11, same user approval)

The above transfer has now also been exercised end-to-end with **new**
provider responses (not earlier whole-source captures), on isolated
disposable copies of the committed synthetic canonical Notes.

- **F06** `Hoy vi a Ana y compré pan.` — **COMPLETED** with genuine
  GPT-6 Router, one genuine GPT-6 Temporal call, two separate GPT-5.6
  Core plans and two independent Core fact reviews. Both distinct facts
  were physically verified in the **same synthetic Day note**. Cost
  estimate for this try: USD 0.0059360; frozen source-bound provider
  record `benchmarks/application_router/scoped_routing_v2/F06.json`.
- **F04** `Mañana iremos al parque a las 12 y luego a las 18 iremos al
  cine.` — the first fresh attempt after the handoff was **FAILED**
  when the original Temporal model returned an unnormalized clock. After
  adding opt-in exact date/clock composition, the next attempt was
  **PARTIAL**: first fact persisted, while the second Temporal response
  included a non-anchoring ordering connector as UNSPECIFIED. That
  exact response is retained as
  `scoped_routing_v2/F04-earlier-partial.json`.
- **F04 final approved attempt** — **COMPLETED**, with two separate Core
  plans/reviews and two separate Temporal interpretations, the second
  using a validated first-route inherited exact date. The provider
  returned only original local temporal wording, including 12:00 and
  18:00 on the same day. Both writes passed canonical Markdown readback.
  The general opt-in Temporal prompt now differentiates pure order
  connectors from material date/time mentions; ordinary historical
  Temporal prompting is unchanged. Estimated cost of final attempt:
  USD 0.0071354. The final real outputs are frozen at
  `scoped_routing_v2/F04.json`.
- Both F04 outcomes and F06 are regression-tested with **all actual
  saved provider outputs** under
  `tests/runtime/test_scoped_temporal_real_provider_replay.py`. This
  tests saved authentic calls, NOT a claim of additional live calls.
- The cumulative estimated provider spend is **USD 0.2273444** out of
  the previously authorized total USD 0.25; no more model retries are
  planned for these two tests. The original 25 cases remain saved with
  their initial outcomes and original source formats.

No changes to active DEV, PROD, personal Notes, model versions or n8n.
Remaining independent follow-up: extend fresh split-input model coverage
beyond F04/F06, particularly lexical subject ownership, user tasks,
polarity/corrections, F27 bad inheritance, and approximate/non-exact
temporal resolutions; do not downgrade Core's write guards.


## Verified Core subject/predicate continuation (2026-10-11)

Subsequent fresh split-input regression F23 uncovered a new boundary:
Router can express an inherited source subject either as
`inheritance:[subject/from_unit]` or as an explicit second candidate
`scoped_source.subject` referring to **the same original text span**.
Both are valid lexical provenance when their offsets/digest match the
original; neither is independently canonical identity authority.

The test-only scoped executor now additionally tracks a
`ScopedCoreSubjectHandoff`, minted only **after** an ordinary Core
fact-bearing WRITE completes and `readback_core_facts` verifies that
fact's exact request/ordinal marker in canonical Markdown. It requires
a unique source subject with the same exact original offsets, a single
actual persisted Core write target, a canonical subject name grounded in
that source mention, and a currently unique canonical Note ID/name/type
with a full-content guard. It refuses attempts to transfer a subject
that merely appeared in Router's lexical hints.

Later separate fragments receive one bounded
`CoreVerifiedInheritedSubject`: source text/offsets, actual canonical
name/type, and a **read-only prior verified fact**. The stable Note ID
and content guard are NOT sent to the model, and the previous sibling
is NOT pasted back as a new user request. An independently rechecked
`CoreInheritedSubjectWriteGuard` permits only one atomic same-target
fact write and rejects missing/stale canonical Notes, guessed targets,
cross-note writes, or multi-action smuggling. Core's independent fact
coverage retains source-object/location lexical checks and rejects extra
unsourced words. The earlier property validator now permits multiple
independently grounded source anchors; it no longer assumes every
property source must have exactly one subject anchor.

F23, with authentic new Router replies citing the same subject span
twice, now writes the first fact to the synthetic `Odyssey` Note in
one full real-provider run. Its second Core model call was **not
completed** in that run; the bounded provider budget gate prevented
an additional recorded response. This is not evidence of a model
semantic rejection. All raw outputs and observed results remain
frozen as `scoped_routing_v2/F23-latest.json`. Earlier F23-v2
Core ESCALATE outputs are separately preserved in
`scoped_routing_v2/F23.json`: replay after the first source
validator correction proves the first property writes and the second
is explicitly NEEDS_ATTENTION. The opt-in application boundary now
translates a typed `PlannerEscalation` into safe NEEDS_ATTENTION
instead of a misleading TypeError/FAILED result, with zero writes
for that route.

Deterministic full Writer + readback acceptance:
- F23: two separate Core fragments produce two verified facts in the
  same canonical Odyssey project Note, if both Core plans are safe.
- F25: a house property and a second same-house repair-need assertion
  can be recorded separately in the same canonical house Note, without
  implicitly creating a Task or marking an operation complete.
- F16: a new local subject, Luis, is never silently bound to Ana just
  because the two share `compró entradas` in the original sentence.
  Typed inherited predicate/object/transaction context alone is not
  enough to certify an independent action by Luis, so that route
  stays blocked until a Core-verified predecessor-event carrier is
  implemented.
- Stale canonical Markdown, a different target Note ID, a missing
  completed predecessor, and multiple atomic writes are rejected.

The Core subject handoff is intentionally **same-target only**:
cross-subject parallel events, Day-note continuations citing a
separate subject and pronoun+subject composite guards still require
independently reviewed general contracts. No automatic use of
untrusted lexical pronouns, task modality or negations was added.
The pre-existing per-route split remains unchanged, as do active
DEV/PROD, model versions and all personal Notes.

The current cumulative estimated authorized provider spend is
**USD 0.2357768 / 0.25** (not an OpenAI billing statement). All
new tests and corrected adapters continue to run without API calls.


## Core-verified event handoff to a different subject (2026-10-11)

An additional independent, opt-in route-local contract now handles the
**bounded affirmative purchase ellipsis**:

`Ana compró entradas para el concierto y Luis también.`

Router still makes two exact user-source routes. In the first route,
ordinary Core and its independent candidate→fact reviewer authorize
and physically write `Compró entradas para el concierto.` to Ana's
canonical Note. A successful complete write is not enough by itself:
`ScopedCoreEventHandoff` requires an independently verified Markdown
readback marker, a unique actual canonical predecessor Note,
one explicit source subject and three EXACT source roles
(`predicate`, `object`, `transaction`). The verified Core fact must
match those three roles in **word order and multiplicity**, not merely
token-set overlap. Negations, conditional scope, unrelated or truncated
source roles are not certified as transferable events.

The second fragment ` y Luis también.` carries only source-verified
external predicate/object/transaction coordinates; the runtime can
attach one `CoreVerifiedInheritedEvent` after checking all three
coordinates against the original message SHA-256 and an earlier
physically verified Core event. It does **not** carry Ana's identity as
the new subject. The previous Note ID and content guard are private
to the writer and are NOT sent to the LLM. The context visible to
Core is its own current fragment plus read-only event evidence; no
sibling request is concatenated into the model input.

The ordinary Core planner and candidate graph reviewer remain the
only plan/coverage authorities. A separate `CoreInheritedEventWriteGuard`
requires exactly one atomic affirmative purchase fact, identical
normalized event wording, a distinct explicitly named NEW subject,
a separately preflight-resolved EXISTING canonical person Note with
the same name, and a fresh unchanged predecessor Note guard.
It refuses mismatched destinations, new creations, more than one
fact/action, altered/reordered/duplicated event text, negative or
conditional clauses and stale previous Notes. A missing predecessor
Core write cannot authorize any second-fact planning or mutation.
It is intentionally a **narrow supported ellipsis**: other event
kinds, tasks, alternate grammatical constructions and composite
identity+event dependencies remain pending, not guessed.

Deterministic acceptance exercises the complete scoped executor,
Core's real writer, readback and thirteen canonical synthetic Notes,
for BOTH saved, authentic GPT-6 Router shapes. Tests include
two different existing buyers, failed first Core operation, wrong
destination, duplicate or rearranged event wording, invented negation,
unrelated action and stale previous Note content. The new Router
provider output is preserved in
`benchmarks/application_router/scoped_routing_v2/F16-router-only.json`.

A single approved real-provider F16-v2 attempt used GPT-6 Router,
then stopped BEFORE the first Core provider call. The budget gate
conservatively reserved ~USD 0.01408 for that request, but after
Router's USD 0.0003201 cost only ~USD 0.01390 remained. Thus this
attempt is **not** evidence of a real Core semantic failure or a
fresh-model end-to-end success. The estimated total accumulated
provider cost is **USD 0.2360969 of the approved USD 0.25**.
Do not weaken the spend cap or make an unauthorized retry to
manufacture a green result.

The historical split architecture, original full-source Router only,
Temporal date proof, same-subject canonical proof, independent Core
semantic coverage and verified Markdown Writer remain unchanged.
DEV, PROD, model choices and the user's personal Notes are untouched.
