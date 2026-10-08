# Router dependent-route continuity — October 2026

Status: **DEV implementation in progress. No activation until verified.**

## Objective

Prevent anaphora/ellipsis inside one user message from losing a person/subject
when Router splits the message, while still executing unrelated fragments with
parallel read-only preparation. Example: `Hoy he hablado con Eric de Prueba.
Mañana vendrá conmigo al cine. El sábado volveré a verlo.` Existing traces show
the middle Day fact was stored without an Eric link even though other branches
completed.

## Accepted authority boundaries

- Original request remains an exact ordered partition; Router never rewrites the
  source, injects an unproven name, resolves identities, or authorizes mutation.
- Router can declare bounded backward dependency metadata but may not decide
  which note/entity that reference resolves to.
- Dependent execution must wait until predecessors complete; independent route
  preparation retains two-worker concurrency, and all Core/Git mutation remains
  serial and idempotent under one outer request.
- Only Core-grounded canonical note identities may serve as dependent reference
  evidence. If no unique, current, evidenced referent can be proven, stop the
  dependent write and make uncertainty visible; never choose arbitrarily.
- No implicit promotion of a dated activity into a person's durable profile.
  Core remains the generic writer and owner of fact placement.
- No replay of a successful predecessor when a dependent clause fails. No
  per-name/specific-verb rules, implicit context leakage or hidden mutable cache.

## Acceptance criteria

1. Exact source partition, bounded backward-only acyclic references, and
   disabled/unknown app rejection are deterministic.
2. Independent route preparation still overlaps; dependent preparation starts
   only after required successful predecessor results are authoritative.
3. Typed identity evidence is uniquely verified against current canonical note
   content, including aliases and newly created notes, before dependent writes.
4. Ambiguous identities (e.g., two names), failed/stale predecessors, or missing
   references block only dependent branches and cannot produce invented links.
5. Replayed outer deliveries cannot repeat committed predecessors; route graph
   shows dependencies and legitimate blocked/failed/complete states.
6. Unit, contract and vertical provider-free regressions cover Eric, sibling
   branches, existing/new names, duplicate-name ambiguity, failed predecessor,
   partial writes, and replay. Production prompt/schema changes require a focused
   explicit bounded live Luna gate before claiming readiness.

## Out of scope

Automatic linguistic reconstruction; additional LLM calls; new infrastructure;
rewriting real user notes; bulk rollbacks; fixing unrelated Tasks or Temporal
usage/cost telemetry.

## Open decision

None for a closed, non-executing internal dependency representation and safe
predecessor gating. **Provider activation remains gated** by focused live evidence
and proof of faithful downstream Core reference binding.

## First safe implementation slice

`Route.depends_on` is an optional internal zero-based reference to one earlier
route. Local validation rejects non-integers, negative values, self references,
forward references, and references outside the plan. It is intentionally not part
of the Router provider JSON schema or prompt.

The runtime prepares only dependency-free routes in its existing two-worker pool.
It executes predecessors once in source order and marks a dependent route blocked
when its predecessor fails. A successful predecessor is also insufficient to run a
dependent route in this slice: no typed, current Core-canonical antecedent handoff
exists yet, so the route is blocked with
`ROUTE_DEPENDENCY_CANONICAL_EVIDENCE_UNAVAILABLE`. The runtime neither supplies
sibling source text nor infers an identity from it. Unrelated routes still execute.

Follow-up activation requires a narrow Core-owned, typed canonical-reference
handoff that is verified at dependent execution time, plus the authorized focused
production Luna gate before any provider output contract is changed.

## Milestone B — Core-private persisted-reference carrier (implemented in DEV source)

Core now retains `CanonicalReferenceEvidence` only on the in-process typed
`ApplicationResult` / `ActionResult` result objects. It is not part of runtime
serialization, web delivery, pending-work records, presentation projections, Router
schemas, or prompts. It is a candidate input for a later Core-to-Core dependent-route
handoff, not a public continuity feature.

For one `WriteAction`, Core considers an item only when all of the following are true:

- the exact source `KnowledgeReference` has a resolved trusted preflight UUID and its
  source fact was rendered through the validated reference renderer;
- the corresponding fact-bearing `UnitResult` succeeded materially, and the post-write
  authoritative source Markdown contains that exact rendered fact at this request's
  deterministic atomic-fact ordinal;
- both the persisted source Note and the referenced canonical Note can be uniquely
  re-read and schema-validated after the write; Core retains their current content guards,
  plus the target UUID, type, canonical name, exact source mention, and source coordinates;
- the source wording is the canonical name, not an alias; the fact-bearing source
  may not be a `reference_lookup_only` helper, but an actual Core-bound reference-only
  **target is permitted** when its link appears in the persisted fact (as required for
  Calendar Day facts that reference an existing person without modifying that person).

Duplicate target UUIDs are rejected rather than selecting an occurrence. Failed, deferred,
pending, bulk, synthetic complete-set/relation helper, duplicate/no-op, alias, malformed,
missing, deleted, or stale cases yield no carrier item. The source-fact check makes result
membership depend on actual persistence, not affected-note IDs, planner text, a display
projection, or a preflight decision alone.

### Exact next-step contract and limitations

A later **Core-owned** dependent executor may accept at most one such carrier item only after
it re-reads both Notes, verifies the two guards, UUID/type/canonical-name identity, and the
persisted source fact. It must then pass bounded typed evidence—not sibling text or a raw ID—to
ordinary Core planning/reference binding. Absence, duplicates, guard mismatch, alias wording,
or any stale/missing Note must block the dependent branch with visible uncertainty.

This milestone does **not** bind `él`, invoke a dependent planner, change `Route.depends_on`
scheduling, change a Router provider schema/prompt, or activate any production behavior. The
future handoff still needs its own Core plan-boundary contract, vertical dependent-route tests,
and the separately authorized focused Luna gate before activation.

## Architecture challenge

**PROCEED, with activation guard.** A simple 'merge adjacent dependent routes'
was already live-tested and failed at Core reference-marker planning. Passing
full sibling text to every planner would also violate per-route source authority.
The smallest structural route is bounded backward-only dependency evidence plus
ordered authoritative Core result lookup, keeping existing n8n/Git/Temporal
ownership. Build closed parsing/validation and provider-free scheduling first;
only activate new model output after there is a validated narrow Core handoff.

## Milestone A — internal fail-closed route graph (implemented in DEV source)

- `Route.depends_on` is a nullable *internal-only* zero-based predecessor ordinal;
  production router's prompt, JSON response schema and parser do not emit or
  accept this field. It is not live-capable until the next gated phase.
- Local validation rejects negative, non-integer, self, forward or out-of-bounds
  dependencies before execution. Backward references cannot form cycles.
- Independent routes continue through the existing parallel preparation and
  ordered Core/Git execution. Dependent branches never enter independent
  preparation and currently return `NEEDS_ATTENTION` after their predecessor:
  `ROUTE_DEPENDENCY_PREDECESSOR_NOT_COMPLETED` or
  `ROUTE_DEPENDENCY_CANONICAL_EVIDENCE_UNAVAILABLE`.
- No predecessor output is yet presented to the dependent planner; this is
  intentional fail-closed behavior, **not referential resolution**. The only
  current observable behavior from the live provider remains unchanged.
- Unit, local validation, and vertical disposable-vault regression tests show
  that declared dependent clauses do not write ungrounded facts while unrelated
  clauses still persist. A separately authorized live candidate gate is needed
  after Core-owned identity evidence and downstream integrity checking exist.

**Verification on the Raspberry outside Codex's networking sandbox:**
`python -m pytest -q`: 1936 passed, 80 skipped, 52 subtests;
`node --test tests/odyssey_web_*.test.mjs tests/odyssey_workflow_partial.test.mjs`:
123 passed; changed-file Ruff lint/format and `git diff --check` passed.
No runtime deployment or user-data rewrite is implied by this milestone.
