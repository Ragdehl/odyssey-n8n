# Application Boundary + Router v0

Status: **approved architecture contract; Slices 1-5 implemented and deterministically validated; Slice 6 Attempt 3 exposed Router-low instability plus a rejected recut Calendar schema; an app-native Calendar schema + Router Luna-medium Attempt 4 is now prepared provider-free and requires separate live authorization**.

## Objective

Introduce the smallest application boundary that lets Odyssey add Calendar, Tasks, Events, and later capabilities without making the established Core planner absorb each application's domain contract.

The central invariant is:

```text
adding, disabling, or removing an application
must not change the Core planner contract
or make ordinary Core READ/WRITE unusable
```

Applications may depend on stable Core services. Core must not depend on application modules for startup or ordinary knowledge behavior.

This phase is a prerequisite for Calendar v0 routing and for Tasks, the first lifecycle-heavy application.

## Non-goals

- no marketplace, package manager, signing, sandbox, or third-party permission model;
- no dynamic code download;
- no general workflow/DAG engine;
- no new canonical database or application-owned knowledge authority;
- no rewrite of the established Core planner;
- no production deployment as part of the initial design/implementation;
- no automatic migration or deletion of data when an application is disabled.

## Dependency direction

The intended dependency graph is one-way:

```text
                 Odyssey Core
          identity / schema / mutation
        Markdown / Git / indexes / temporal
             ^        ^         ^
             |        |         |
         Calendar   Tasks     Events
```

`odyssey_core/` owns reusable knowledge/platform primitives. Application-specific routing, planners, lifecycle rules, projections, and optional UI belong outside Core.

The current Temporal Foundation remains a valid Core dependency: normalized dates/date-times, timezone context, ranges, and deterministic Day-reference primitives are reusable below Calendar, Tasks, and Events. Calendar-specific routing/query/presentation logic is not a reason to move more domain behavior into Core.

The implementation uses `odyssey_apps/` as the application package boundary. Runtime composition may discover/enable applications; `odyssey_core/` must not import application packages.

## Request flow

When at least one application capability is enabled, ordinary natural-language requests pass through a small router before detailed planning:

```text
user request
    |
    v
Router (GPT-6 Luna)
    |
    +--> Core route ------> established Core planner
    |
    +--> Calendar route --> Calendar planner
    |
    +--> Tasks route -----> Tasks planner
    `--> no safe route ---> fail closed / clarify
```

Explicit application entry points or future `@App` syntax may bypass model routing deterministically when the destination is unambiguous and enabled. Runtime may bypass the router only when no specialized application is registered at all. A registered but disabled capability remains visible to routing as unavailable evidence so specialized intent cannot silently fall through to Core.

## Router model boundary

The v0 router uses **GPT-6 Luna**. The initial `low` reasoning candidate did not prove stable enough: the same dependent temporal-owner case passed in Attempt 2 and regressed to Core again in Attempt 3 under an unchanged routing contract. The current provider-free successor therefore raises Router reasoning to `medium` rather than growing the prompt with case-specific rules. There is no automatic Sol fallback in Router v0 unless later evidence separately justifies one.

New application planners also start with GPT-6 Luna. Their reasoning effort is validated per application; Calendar should begin with the smallest sufficient configuration. This phase does **not** switch or edit the already accepted Core planner model/prompt/Structured Output contract.

The router is intentionally much smaller than a planner. It may decide only:

- whether the request needs Core or one enabled application capability;
- whether independent material intentions need separate routes;
- which exact source text belongs to each route;
- whether routing is unsafe/ambiguous and should fail closed.

It must not resolve identities, inspect the vault, invent facts, choose canonical Note targets, generate Markdown, normalize dates, decide CREATE versus UPDATE, or execute any mutation.

## Minimal application manifest

Router input is generated from registered application manifests plus runtime availability. A v0 manifest needs only compact routing metadata, for example conceptually:

```text
id: calendar
routing_description: day/date-owned occurrences and Calendar navigation
dependencies: [temporal]
enabled: true | false   # runtime state, not app prompt detail
```

Detailed application prompts, schemas, lifecycle states, storage details, examples, and UI instructions are not included in router context. Disabled registered applications may contribute only this same compact descriptor plus `enabled=false`; they are not routable execution targets. This lets Router return `NEEDS_CAPABILITY` instead of silently forcing specialized intent through Core. A future true uninstall/package lifecycle is outside v0.

`core` is a built-in routing destination rather than an installable application. Its compact description covers ordinary Odyssey retrieval/mutation and existing generic delegation semantics not owned by an enabled application.

## Route-plan contract

The router preserves user wording rather than paraphrasing work for downstream planners. Conceptually:

```text
RoutePlan
  outcome: ROUTE | CLARIFY | NEEDS_CAPABILITY
  routes:
    - capability_id
      source_text
```

For `ROUTE`, every `source_text` must be an exact substring of the original request. Local validation maps those substrings back to the request in order and rejects rewritten, overlapping, fabricated, or out-of-order route text. Collectively, ordered routes must cover every non-whitespace character of the request exactly once; only whitespace may remain between adjacent route spans. This makes dropped negations, qualifiers, conjunctions, or punctuation a local validation failure rather than silent semantic loss. Each downstream planner receives its exact routed `source_text` as the current authoritative request plus the normal bounded prior-turn conversation context. It does not receive sibling route text or the full current message as an alternate semantic authority. If current-message wording is required to interpret another clause safely, those clauses are dependent and must remain in one route.

`CLARIFY` means the enabled capability set admits more than one materially different safe route and guessing would change behavior. `NEEDS_CAPABILITY` means the request is understandable but clearly requires specialized lifecycle/operation semantics that neither Core nor an enabled application can safely provide. Neither outcome executes work.

The router never emits stable IDs, note types, properties, dates, facts, app-internal commands, or execution arguments.

## Splitting rule

The router splits only **independent material intentions that require different capability owners**. It does not split merely because a sentence has several clauses, and it does not create extra model calls for multiple ordinary Core facts that the Core planner can already handle together.

Example:

```text
"A Cloe le gusta el chocolate y mañana viene el fontanero."

route 1 -> CORE
  "A Cloe le gusta el chocolate"

route 2 -> CALENDAR
  "y mañana viene el fontanero."
```

The route spans form an exact ordered partition of the original wording apart from whitespace. A conjunction or punctuation mark therefore belongs verbatim to one neighboring route; the router may not drop it or replace either clause with an interpreted summary.

## Dependent clauses stay together

A request is not split when one clause changes the meaning or execution of another. The route goes to the primary capability whose domain semantics are needed; that capability may reuse Core or declared lower-level capabilities.

Example:

```text
"Marta empieza mañana a trabajar en Airbus."
        |
        `--> one CALENDAR route
```

Calendar understands the temporal meaning, but the canonical knowledge owner can still be Marta. Routing ownership and knowledge ownership are deliberately distinct.

The Calendar planner may therefore produce a shared Core write intent plus a validated temporal reference. Core still resolves Marta/Airbus, validates the mutation, renders canonical links, writes Markdown, records Git/history, and refreshes derived indexes.

Likewise, a future request such as:

```text
"El viernes tengo dentista y recuérdamelo una hora antes."
```

should remain one route when the reminder depends on the event. The selected application may call an explicitly declared lower-level dependency; Router v0 does not build a generic cross-application DAG.

## Application planners and shared Core contracts

Each application owns its detailed planner contract. Application planners may emit:

- application-specific typed intents handled by that application; and
- shared Core intents compiled through reusable Core contracts.

Applications do not reimplement note creation, identity resolution, Markdown persistence, Git history, indexes, or authorization. Shared write semantics should reuse the existing semantic-write/Core mutation contract rather than copy a second Note-creation protocol into every application prompt.

A small shared Core extension is justified only when it is genuinely cross-application. For example, a typed temporal-reference fact part can belong to Core because Calendar, Tasks, Events, Journal, and later capabilities may all need to preserve a normalized date reference while Core alone renders its canonical Markdown representation.

App-specific lifecycle fields or actions do not move into Core merely because an application needs them.

## Execution and isolation

The runtime executes routed units in original request order. Application results return through the existing request/application result boundary so partial completion, safe deferral, observability, and request correlation do not become app-specific reinventions.

An application receives only the Core services its contract needs. Direct filesystem writes or a parallel application database must not become an alternate canonical knowledge path. Canonical personal knowledge continues to mutate only through validated Core boundaries.

The complete RoutePlan is locally validated before any route executes. One outer delivery/request ID remains the idempotence and user-visible request boundary; routed subexecution must not become an independent competing delivery authority. Safe independent routes execute in original order and may complete even when another route later defers or fails. Application failure is bounded to that route. A missing/disabled/failing application must not prevent Core startup or ordinary Core requests from functioning.

Slice 3 preserves that ownership by deriving deterministic internal route locators from the outer request ID plus route ordinal. These locators exist only so request-scoped Core finalizers such as pending work and Git history cannot collide across routed subexecutions; they are never delivery IDs, and the aggregate `ApplicationResult.request_id` remains the outer ID. The current user message is appended to conversation history at most once. Router and every downstream planner receive the same bounded prior-turn context captured before routing. If exactly one routed subexecution produces resumable pending work, clarification state points to that route-local durable record so only that saved route resumes. Multiple route-local pending projections remain fail-closed because the current public result has only one scalar pending-work field.

A future untrusted marketplace requires a separate permissions/sandbox/signing design. Router v0 establishes logical/module isolation only; it does not claim that arbitrary third-party Python is safe to execute in-process.

## Disable/remove behavior

V0 must be testable with Calendar enabled and disabled even though it does not implement a user-facing installer.

When an application is disabled:

- while registered, it remains only as compact `enabled=false` routing evidence and cannot be selected as an executable route;
- its planner/executor/UI entry points are unavailable;
- Core still starts and ordinary Core READ/WRITE works;
- previously created canonical knowledge is not deleted;
- canonical schema compatibility needed to read existing data is not silently removed.

Application disablement is not authorization to rewrite or migrate existing knowledge.

## Core-planner immutability gate

Adding or disabling an application may change the router's dynamic capability catalog, but it must not change the established Core planner contract.

Deterministic sentinels must compare the accepted Core planner artifacts before and after application registration:

```text
rendered Core planner prompt            unchanged
Core planner Structured Output schema   unchanged
Core teaching examples / accepted hash  unchanged
Core production model configuration     unchanged
```

Application work therefore carries router/app regression responsibility without automatically reopening the full Core planner live gate.

## First Calendar consumer

Calendar is the first consumer of this boundary. Slice 4 moved Calendar-specific deterministic query, presentation, and compact descriptor ownership into `odyssey_apps/calendar/`, while the shared Day/date identity, links, ranges, and materialization primitives remain in `odyssey_core/temporal.py`. Runtime composes the read-only Calendar surface instead of owning Calendar projection semantics. Slice 5 now adds the provider-free natural-language Calendar planner/executor contract, but production routing remains deliberately disabled until the focused live gates and later DEV adoption.

Slice 5 is implemented provider-free. Calendar now has its own closed GPT-6 Luna/low planner
contract, exact-date/DATE_RANGE/UNSPECIFIED temporal result shapes, strict local response parsing,
and a routed executor. Exact Day literals are persisted through a small Core-owned Day-capture
primitive using canonical validation, atomic provenance, link materialization, and revision-safe
persistence; Calendar does not write Markdown directly. Entity-owned temporal statements compile
through the existing Core semantic-write path using an opt-in Core temporal-reference fact part,
which renders the canonical Day wikilink only after Calendar has supplied a validated exact date.
The default Core planner prompt/schema/model/examples remain hash-pinned unchanged. `DATE_RANGE`
is preserved as temporal evidence but range-aware natural execution remains deferred; it is never
collapsed to one Day. No provider call or live deployment is implied: the compact Calendar matrix
is frozen for its later bounded GPT-6 Luna gate.

Representative routing expectations:

| Request | Router result |
| --- | --- |
| `A Cloe le gusta el chocolate` | CORE |
| `Mañana viene el fontanero` | CALENDAR |
| `A Cloe le gusta el chocolate y mañana viene el fontanero` | CORE + CALENDAR, ordered independent routes |
| `Marta empieza mañana a trabajar en Airbus` | one CALENDAR route; Calendar may emit Core-owned write + temporal reference |
| `Escribe en mi diario que hoy fui al trabajo` | CORE/Journal semantics, not Calendar merely because a date is present |
| request requiring unavailable specialized lifecycle semantics | NEEDS_CAPABILITY rather than unsafe approximation |

Calendar's detailed planner receives only after routing and starts on GPT-6 Luna. It may use shared Core write definitions plus Calendar-specific typed output; it must not write Markdown directly.

## Deterministic acceptance criteria

1. Registering/enabling Calendar changes no accepted Core planner prompt/schema/model artifact.
2. Disabling Calendar leaves Core startup and ordinary READ/WRITE deterministic tests green.
3. Router output is closed, validated, ordered, and carries only enabled capability IDs plus exact source text.
4. Rewritten/fabricated/overlapping/out-of-order/incompletely covered routed text fails closed locally.
5. Independent Core + Calendar intents can be split without duplicate execution.
6. A single dependent temporal/Core statement remains one route and preserves one canonical knowledge owner.
7. Application code cannot bypass the validated Core mutation boundary to mutate canonical knowledge.
8. App failure/unavailability is reported as bounded route failure and does not poison unrelated Core routes.
9. Router/app model failures make no canonical mutation unless a complete validated downstream intent already exists.
10. No new application requires editing the Core planner instructions merely to become routable.

## Model-facing validation

Router and each new application planner are separate model-facing contracts. Deterministic schema tests come first; live evidence is collected only after implementation is otherwise settled.

Router v0 should freeze a compact GPT-6 Luna regression matrix covering at least:

- ordinary Core-only request;
- Calendar-only request;
- one independent Core + Calendar split;
- one dependent statement that must stay together;
- Journal/date wording that must not be stolen by Calendar;
- unavailable specialized capability;
- ambiguous routing that must not guess;
- meaningless input that produces no executable route.

Calendar planner gets its own separate GPT-6 Luna gate for its detailed semantics. A router pass is not evidence that the Calendar planner is safe, and vice versa.

Application planners are domain-local: they do not classify or name sibling applications. The Router alone knows the application catalog; a planner that receives foreign-domain semantics fails closed with a generic app-local `OUT_OF_SCOPE` result.

Slice 6 Attempt 1 ran at commit `f5949ec` after explicit bounded-cost authorization: 16/16 permitted Luna/low calls, zero retries, Router 7/8 and Calendar 4/8, for 11/16 overall. Review found all five failures to be candidate-contract/model failures rather than oracle drift. The retained evidence is owned by `benchmarks/application_router_calendar_live_v1/`. Review then removed sibling-application vocabulary from Calendar entirely. The Router v1 matrix remains unchanged; the consumed Calendar v1 matrix remains immutable historical evidence, while Calendar v2 changes only foreign-domain failures to generic `OUT_OF_SCOPE`. Attempt 2 then ran once at `459956a57770fd4e55c3dab75fa9cd7c58320e2b`: Router passed 8/8, Calendar passed 6/8, and the overall gate failed. The two remaining Calendar failures showed that foreign-domain semantics could still consume temporal handling or reach an over-broad shared Core-write schema. Attempt 3 therefore keeps Router v1 and Calendar v2 oracles unchanged while restricting Calendar Core writes to generic fact-only record operations over untyped identities, with duplicate local validation. Attempt 3 then ran once at `3319f6d4d1ec389140b7c722e70ab9670ce948dd`. Router completed 8/8 calls but only 6 matched the exact oracle: one mismatch was separator-whitespace allocation within a valid exact span, while the dependent temporal statement materially regressed to Core. Calendar produced no completed provider response because the narrowed schema failed at the provider boundary in every case. This is not Calendar semantic evidence. No retry or continuation was made. Attempt 4 is prepared provider-free with those two corrections: Calendar owns a genuinely app-native identity/fact/time schema that is expanded locally into the shared Core semantic-write contract, and Router remains GPT-6 Luna but uses `medium` reasoning. Router v2 changes no cases or owners; it only treats boundary whitespace as equivalent after the production exact-span validator has already accepted the plan. Attempt 4 requires fresh bounded-cost authorization before any provider call.

Before either live gate, calculate a bounded maximum call count/cost and request explicit human authorization. No live gate gets mutation authority over personal data.

## Proposed implementation slices

1. **Boundary skeleton.** Introduce the application package/registry boundary and enabled-capability catalog without changing request behavior.
2. **Router contract.** Add closed RoutePlan types, exact-source validation, GPT-6 Luna adapter, deterministic fake-model tests, and Core-planner immutability sentinels.
3. **Runtime composition.** Route Core requests through the unchanged Core planner and support bounded ordered multi-route aggregation; no Calendar planner yet.
4. **Calendar extraction.** Place Calendar-specific planner/executor/query ownership behind the application boundary while keeping reusable Temporal Foundation in Core.
5. **Calendar natural routing.** Implement Calendar's GPT-6 Luna planner and its typed Core/Calendar intents; add deterministic vertical tests.
6. **Focused live gates.** Run one bounded Router gate and one bounded Calendar-planner gate only after deterministic validation and explicit cost authorization.
7. **DEV adoption.** Deploy only to isolated DEV, perform browser/chat E2E, and preserve any discovered failure as regression tests before readiness.

## Architecture challenge before implementation

Before Slice 1 code, run the repository architecture challenge against this contract. The challenge must specifically test whether the proposed router is doing planning work, whether application code can become a second mutation authority, whether disabling Calendar truly leaves Core usable, and whether the physical module boundary matches the dependency direction.

## Architecture challenge result

**PROCEED**, after three bounded corrections incorporated into this contract before implementation.

The challenge confirmed that a pre-planning router is justified: the existing `DelegateAction` occurs only after the Core planner has already interpreted the request, so using it as the application selector would either require application rules inside the Core planner or allow confident Core misrouting. n8n remains integration/orchestration and must not become the semantic router. No new service, database, generic DAG, or plugin framework is needed.

The challenge found and corrected three boundary risks:

1. A disabled registered capability cannot simply disappear from all routing evidence while `NEEDS_CAPABILITY` is expected to distinguish specialized unsupported work. Registered disabled apps therefore expose only compact `enabled=false` routing evidence and can never be execution targets.
2. Passing the full current message to every downstream planner would weaken route authority and risk sibling-intent leakage. A downstream planner receives only its exact current route plus normal bounded prior-turn conversation context; clauses needing each other must remain one route.
3. Multi-route execution must not create competing delivery/idempotence authorities. The whole RoutePlan validates before execution and one outer request/delivery ID owns the aggregate result while independent routes may complete or defer separately.

The current Core temporal/Day-reference primitives remain justified shared infrastructure: Core atomic-fact capture chronology and canonical materialization already use the deterministic Day-link contract, and later Calendar/Tasks/Events reuse the same temporal identity. Calendar-specific query, planner, routing, executor, and UI ownership should nevertheless move behind the application boundary where currently coupled.

No further material product, source-of-truth, schema, security, or infrastructure decision is required before Slice 1.

## Resolved v0 product decisions

Human review settled the remaining v0 choices before implementation:

1. **Partial execution:** independent safe routes may execute even when another independent route needs clarification or fails. The aggregate result reports partial completion; no unrelated successful route is rolled back merely to preserve all-or-nothing behavior that the user did not request.
2. **Router conversation context:** Router receives the same bounded recent visible conversation evidence needed for continuity, but that evidence is routing-only and never canonical truth or mutation authority. Routed current-message source text remains exact and locally validated.
3. **Explicit app syntax:** `@Calendar` / `@Tasks` routing is deferred. Automatic routing is the v0 product behavior; explicit bypass syntax should be added only if real use demonstrates a control/disambiguation need.

These decisions close the product-contract questions required before implementation.
