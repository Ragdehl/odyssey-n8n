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
