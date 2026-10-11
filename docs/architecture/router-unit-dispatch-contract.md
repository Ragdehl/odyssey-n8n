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
