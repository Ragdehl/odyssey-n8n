# Router bounded parallel interpretation — DEV phase (2026-10)

## Architecture challenge: PROCEED with a bounded first slice

Observed example: `Hoy tengo que ir al cine y mañana ire al teatro` was correctly split into
Tasks and Temporal routes. Real request telemetry showed 8.38 s Router and 15.28 s
subsequent sequential route work (25.71 s browser total). Parsing and preparing
independent route interpretations do not need access to canonical Markdown mutation.
Today `execute_routed_request()` executes complete routes sequentially. A naive thread
pool around that loop would run concurrent Core/Git writes and violate canonical
ordering/idempotence; it is prohibited.

**Approved aim:** Parallelize independent, model-only preparation while leaving one
serialized Core write authority. Do not redesign Router, Tasks, Temporal or Core.
**Slice 1:** Up to two concurrent application interpretation jobs for separately
validated Router spans. Each job receives its own exact span and immutable prior-turn
context. It may call the existing Tasks/Temporal interpreters, never Core execution,
repository/index reads, persistent state, Git, or pending-work writes. Results are
consumed in route order by the existing executors and aggregated under one delivery ID.
If an interpretation crosses midnight before its serial execution, discard it
and reinterpret at execution time with the new clock. No stale date interpretation
may reach Core. The feature is disabled by default and explicitly enabled only
in the isolated DEV service with `ODYSSEY_PARALLEL_ROUTE_PREPARATION=1`.
Every route still passes the same Core validator/mutation boundary. A route whose
preparation fails remains a bounded failed route; unrelated routes proceed as before.
Synchronous single-route and unsupported-route execution is unchanged. Tasks
interpretation can overlap Temporal interpretation in another route; a Tasks
route that itself needs Temporal calls Temporal in its serial executor, for now. Keep one request
lock and the existing route-local IDs, pending-work and Git semantics.

**Acceptance:** deterministic barrier test proves two interpretation jobs overlap and
commit callbacks remain ordered; failures are isolated; route/correlation validation,
fixed prior context, replay/clarification and disabled destinations are unchanged;
real Core/Calendar fixture persists two independent Day facts correctly; all existing
tests pass. A measured DEV replay of the actual user example determines real speedup
versus the same configuration sequentially. Do not advertise estimated speedup as measured.

**Out of scope for slice 1:** parallel Core planners/preflight/writers, concurrent writes,
provider prompt changes, complex route DAGs, new services, independent deliveries,
multiple concurrent clarifications, global HTTP/request concurrency changes.

**Later Core-related slice (separate decision):** Only after slice 1 is stable, define a
pure shared Core planning artifact and serial apply/revalidation contract. This would
allow concurrent Core planner API calls but requires new temporal/time snapshot rules,
provider telemetry, read-after-write semantics, index freshness and stale target guards.
It must not be simulated by concurrent execution of the current complete Core call.

## Slice 2 — validated Core model planning in parallel (October 2026)

Approved follow-up after Slice 1: each bounded route's worker now completes both its
specialized interpretation when applicable (Tasks / Temporal, including
Tasks-dependent Temporal) **and the ordinary Core Luna-first RequestPlanner
call**, including routes sent directly to Core, with its existing Sol
fallback and Tasks' ordinary `TaskCorePlanner` contract where applicable. Workers
may only call model providers, inspect immutable schema and route context, and
construct validated typed plans. No canonical vault, index, identity selection,
preflight, Git, pending work or mutable delivery state is touched in these workers.

A request-local `_PrecomputedCorePlan` carries the exact routed source, domain
interpretation, frozen clock and already-validated result (or provider failure),
plus bounded usage/latency evidence. A `_PreparedPlanner` replays that result
through the **existing** `execute_request()` Core boundary, not through a new
mini-planner or direct writer. A model error is replayed as the existing failed
planning result; a clarification remains a Core clarification; none triggers an
unintended second model request. Every write is re-resolved and validated at its
actual serialized execution time, after prior route commits. Sibling routes
may target the same Day/note without concurrent writers or lost updates.

No cross-route semantic dependencies are inferred: Router's existing exact-source
segmentation is the sole authority. Tasks/Temporal special operations without
Core-planned writes (queries / Work Sessions / unresolved Temporal) continue through
their existing executor in order. A change in calendar date between planning and
commit discards that prepared result and runs the original serial path, so relative
phrases cannot silently use a stale day. Single-route behavior is unchanged.

The existing `ODYSSEY_PARALLEL_ROUTE_PREPARATION=1` flag gates both slices in isolated
DEV; it remains off by default elsewhere. Recorded planner call duration and
provider tokens survive preplanning, although overlapping stage durations must
**not** be added together to infer end-to-end wall time. Actual speed gains are
pending a controlled comparison of equivalent DEV inputs; deterministic tests
prove concurrency and semantic safety, not API-network speed.

Regression coverage: runtime composition verifies Tasks and Temporal core-planner
calls overlap in different workers without a repeat during serial commit; provider
failure remains isolated; `test_temporal_user_path_e2e.py` verifies that concurrent
model plans targeting the same Calendar Day are committed without lost updates.
Existing clarification/idempotence and Core identity guards remain the authority.

**Rollback:** remove the optional preparation injection or turn off the DEV flag;
existing synchronous routing remains authoritative. Keep the change on `dev` only
until verified. Never touch real vault files or production to benchmark.
