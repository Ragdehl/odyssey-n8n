# Phase 17 semantic request records

Status: **planned Phase 17 application-boundary capability; not implemented**

## Objective

Persist one small Markdown record for each logical Odyssey user request so the user can later retrieve not only canonical knowledge, but also the history of what they asked Odyssey to do, how the validated planner decomposed the request, and what knowledge objects were affected.

This adds a queryable conversational/action-history dimension without making raw execution logs part of normal knowledge retrieval.

```text
logical user request
        |
        v
validated RequestPlan
        |
        v
Phase 17 execution
        |
        +--> canonical knowledge changes/results
        |
        `--> one user_request Markdown record
```

## Representation

The preferred initial direction is to reuse the existing Markdown note format and canonical note schema rather than inventing a second storage system. Phase 17 may add a controlled canonical type named `user_request` to `config/note-schema.json` after the schema change is proposed and validated in that phase.

A `user_request` record is special application history, not ordinary user knowledge:

- Phase 17 creates it automatically for a logical Odyssey request;
- the ordinary write planner does not authorize creation of `user_request` notes;
- normal knowledge retrieval, entity resolution, bulk selection, and calculations exclude `user_request` by default;
- the same semantic/index machinery may still index these records so explicit history queries can retrieve them efficiently;
- Core, not prompt compliance alone, owns the default exclusion rule.

The simplest safe initial gate is:

```text
normal retrieval
    -> exclude type=user_request

explicit history retrieval
    -> planner explicitly selects type=user_request
    -> Core allows that type-filtered search
```

Do not rely only on the type description telling Sol to avoid these records. The retrieval boundary must enforce the exclusion when no explicit history type is selected.

## Why this belongs in the same schema

Reusing the existing note machinery gives request history the same useful infrastructure with little new architecture:

- stable IDs;
- Markdown source files;
- lifecycle timestamps such as `created_at`;
- schema validation;
- semantic embeddings and query text;
- deterministic type/date filters;
- Git diffs/history once the Phase 17 Git boundary exists.

The special behavior is therefore primarily a **visibility and creation policy**, not a separate database or retrieval engine.

## Intended queries

Examples that should explicitly opt into request-history retrieval include:

```text
"¿De qué hablamos el 12 de agosto?"
    -> type=user_request
    -> created_at range for 12 August

"¿Te acuerdas de qué notas creamos cuando te hablé de Marta?"
    -> type=user_request
    -> semantic query around Marta
    -> inspect created/affected stable IDs from matching request records

"¿Qué cambiaste cuando te dije que Marta se mudaba?"
    -> type=user_request
    -> locate the request record
    -> follow its request_id to the request-level Git change evidence
```

Ordinary questions such as `¿Dónde vive Marta?` must not receive `user_request` records merely because those records repeat the words `Marta` or `Lyon`.

## Minimum semantic content

A request record should preserve human- and machine-useful evidence, not raw model internals. The exact schema fields remain a Phase 17 contract decision, but the initial record should be able to preserve:

- a stable `request_id`;
- the exact user request received by the Odyssey application boundary;
- the validated `RequestPlan` or a deterministic human-readable rendering of it;
- execution status;
- affected stable note IDs, distinguishing created/updated/deleted or failed/deferred work where useful;
- pending/candidate IDs needed to understand partial success;
- request/trace correlation metadata where appropriate.

Do **not** persist hidden chain-of-thought, raw reasoning traces, or every intermediate model response. The validated plan is the auditable semantic decision boundary.

## Relationship with Git

Request records and request-level Git history should correlate through the stable `request_id`.

Do not require a request record included in a commit to contain that same commit's SHA: Git commit hashes depend on the committed tree, so embedding the final hash in the file would create a circular self-reference.

Prefer:

```text
user_request record
    request_id: R123

Git commit metadata/message/trailer
    Odyssey-Request: R123
```

The application can later resolve the commit associated with `R123` when a user asks to inspect or undo that action.

A request that produces no canonical knowledge mutation may still have a useful `user_request` history record. Whether every read-only request produces its own Git commit is an explicit Phase 17 policy decision; do not let Git mechanics determine whether semantic request history exists.

## Storage and indexing

A path such as `_odyssey/requests/` is a reasonable initial namespace, but exact layout should be fixed only with the Phase 17 implementation contract.

The initial architecture should prefer the existing context index rather than a second request-history index, provided the index/query layer can enforce the default exclusion safely. If evidence later shows scale or lifecycle needs are materially different, a separate derived index can be reconsidered.

## Safety rules

- `user_request` is excluded from normal retrieval by Core by default.
- `user_request` is not a normal CREATE target for user knowledge writes.
- semantic similarity alone must never cause request-history records to contaminate ordinary knowledge answers.
- request history does not replace canonical notes; duplicated factual wording in a request record is historical evidence only.
- request records do not replace operational tracing/logging. Tokens, latency, low-level model calls, stack traces, and similar diagnostics remain operational trace data.
- request history should remain queryable even if no knowledge mutation occurred.

## Out of scope for the initial contract

- storing full hidden model reasoning;
- treating request records as ordinary entity-resolution candidates;
- using request records as canonical truth for facts already represented in knowledge notes;
- building a second semantic search engine solely for history;
- automatic unrestricted Git revert from a retrieved request record;
- deciding remote Git backup or multi-device synchronization.

## Open decisions for Phase 17

Before implementation, decide from the application-flow contract:

1. exact `user_request` type properties and which evidence belongs in frontmatter versus body;
2. whether all Odyssey requests, including read-only requests, create a request record;
3. whether the final answer text itself is stored, summarized, or represented only through result IDs/evidence;
4. exact default-exclusion API in `ContextIndex` / `get_context` and other selectors;
5. whether the production planner sees internal types in the same schema projection for read and write planning or through a restricted projection;
6. exact path/name convention;
7. how request records participate in request-level Git commits without circular commit-SHA metadata.
