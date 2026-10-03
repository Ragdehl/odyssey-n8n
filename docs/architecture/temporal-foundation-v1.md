# Temporal Foundation v1 — shared date/time contract

Status: **approved and provider-free complete before Tasks; Calendar prompt/provider schema remain byte-identical, no live model gate is reopened, and no deployment is implied**.

## Objective

Extend the lower-level Temporal Foundation from date-only Calendar needs to the smallest shared
contract required by Tasks and later Events. Temporal remains a Core/platform capability, not an
application, router destination, scheduler, or second planner pass.

The central boundary is:

```text
Router chooses one primary application
             |
             v
      application planner
       /              \
app-owned semantics   shared Temporal contract
       \              /
             v
            Core
 identity / mutation / Markdown / Git / indexes
```

A Task request with temporal wording therefore does **not** execute Calendar first. Calendar, Tasks,
and Events consume the same lower-level normalized temporal contract independently.

## Shared normalized shapes

Temporal v1 defines these application-opt-in result shapes:

```text
EXACT_DATE
EXACT_DATETIME
DATE_RANGE
UNSPECIFIED
```

Applications explicitly choose the subset they support. A future shape does not silently become
executable merely because it was added to Temporal.

Calendar v0 remains date-only and opts into:

```text
EXACT_DATE | DATE_RANGE | UNSPECIFIED
```

Tasks may later opt into:

```text
EXACT_DATE | EXACT_DATETIME | UNSPECIFIED
```

Events may justify additional interval semantics later. `DATETIME_RANGE` is intentionally deferred
until a real consumer needs it.

## Exact date-time contract

An `EXACT_DATETIME` value is an ISO date-time at second precision with an explicit UTC offset, for
example:

```text
2026-10-05T15:00:00+02:00
```

The owning application supplies the current IANA timezone context, for example `Europe/Paris`.
Core Temporal validation verifies that the offset is valid for that local wall time in that zone.
Naive date-times, fabricated offsets, invalid zones, fractional-second ambiguity, and nonexistent
DST wall times fail closed. A repeated local wall time during a DST fold is different: either valid
offset represents a real exact instant, so value validation accepts it. The owning application must
fail closed when the **source wording itself** gives only an ambiguous local clock time; a relative
expression such as "in two hours" may already disambiguate the instant.

The application model may interpret natural wording, but it is never authority for accepting a
malformed normalized value. Temporal validation performs no identity resolution, routing, Task/Event
role selection, persistence, or Markdown rendering.

## Natural-language ownership

The selected application interprets natural temporal wording inside its own bounded planner call.
Temporal v1 is the shared output/validation contract; it is **not** another mandatory model call.

For example, with current context in `Europe/Paris`:

```text
"Crea una tarea para pasado mañana a las 3 para pintar la pared"

Router
  -> Tasks (one route)

Tasks planner
  -> task lifecycle/create semantics
  -> temporal phrase: "pasado mañana a las 3"
  -> shared Temporal EXACT_DATETIME

Core
  -> resolves/creates the canonical Task note and persists validated properties
```

Likewise, `dentro de dos horas` is interpreted relative to the current date/time/timezone by the
owning application planner and must normalize to an `EXACT_DATETIME` before execution. Temporal does
not decide whether that instant means `planned_start_at`, `deadline_at`, an Event start, or some
other domain role. The application owns that role.

## Dependency semantics

Application descriptor dependencies name lower-level capability contracts. They are routing and
composition evidence, **not an execution DAG**. In particular:

```text
tasks.dependencies = ("temporal",)
```

means Tasks may reuse the shared Temporal contract. It does not mean Runtime invokes Calendar, and
it does not authorize Router to emit a Calendar -> Tasks chain. Runtime continues to execute the
single selected dependent route unless the original message contains independent intentions that
Router legitimately splits.

## Calendar compatibility requirement

Extracting the shared contract must not reopen Calendar's accepted live model behavior merely for a
refactor. The existing Calendar planner continues to expose exactly the same provider enum and prompt:

```text
EXACT_DATE | DATE_RANGE | UNSPECIFIED
```

Calendar does not accept `EXACT_DATETIME` until a later Calendar/Event product decision explicitly
requires timed occurrence behavior. Its accepted prompt and Structured Output bytes remain unchanged
by Temporal v1.

## Persistence boundary

Temporal values become canonical application properties only through the owning application plus
Core mutation boundaries. Calendar may later project Task/Event temporal properties onto its visual
surface, but projection does not make Calendar their owner and does not materialize a Day merely
because a structured property exists.

For a future Task, likely distinct domain roles include a target day, planned start/end, deadline,
and actual lifecycle timestamps. Temporal v1 supplies normalized date/date-time values only; Tasks
will define which roles exist and how lifecycle transitions use them.

## Explicitly deferred

- a generic app-to-app workflow/DAG executor;
- a standalone Temporal model call on every dated request;
- recurrence rules;
- reminders/notification delivery;
- comprehensive deterministic natural-language date parsing;
- arbitrary cross-timezone phrases such as "3 PM New York time" until a consumer contract defines
  how explicit foreign zones are grounded;
- datetime intervals until Tasks/Events demonstrates a concrete need;
- timed Calendar grids before Events owns timed occurrences.

## Validation boundary before Tasks

Temporal v1 adds no user-visible exact-date-time operation by itself. There is therefore no truthful
Router -> application -> Core vertical E2E for `EXACT_DATETIME` until Tasks becomes its first real
consumer. Provider-free contract tests cover the new normalized shape and timezone safety, while the
existing Calendar vertical suite proves that extracting the shared date contract does not alter the
current routed Calendar path. Tasks must add the first real exact-date-time vertical regression before
its behavior is considered ready.

## Architecture challenge result

**PROCEED.** The concrete problem is shared normalized temporal evidence for multiple applications,
not cross-application orchestration. Reusing Core Temporal validation plus an app-opt-in resolution
contract is the smallest solution: application planners retain natural-language/domain authority, Core
retains normalized-value safety, and Runtime gains no DAG, service, database, or extra provider pass.
The separate `temporal_resolution` module is justified by immediate Calendar reuse and the approved
next Tasks consumer; broader parsing or scheduling abstractions remain deferred.

## Open decisions

None for Temporal v1. Task-specific roles such as target date, planned start/end, deadline, and actual
lifecycle timestamps belong to the Tasks contract and are intentionally not settled here.

## Acceptance criteria

1. `EXACT_DATETIME` has deterministic offset-aware validation against an explicit IANA timezone.
2. `EXACT_DATE`, `DATE_RANGE`, and `UNSPECIFIED` remain behaviorally unchanged.
3. Applications opt into temporal shapes explicitly; unsupported shapes fail closed.
4. Calendar's provider schema and rendered prompt remain byte-for-byte unchanged.
5. No new provider call, mutation authority, database, or application chain is introduced.
6. A future Tasks planner can reuse Temporal v1 in its existing single app-planner call.
7. Core remains application-agnostic and performs canonical validation/mutation/persistence only.
