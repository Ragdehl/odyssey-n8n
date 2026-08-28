# Phase 17C local Git vault history

Status: **planned Phase 17C capability; not implemented**

## Objective

Use Git as an optional history, diff, audit, and recovery layer around Odyssey's authoritative Markdown vault without making Git the source of truth or coupling per-note domain materialization to version-control commands.

Phase 17A introduces one stable `request_id` for each logical Odyssey request. Phase 17C reuses that same identifier to correlate request-level Markdown changes with local Git history.

```text
logical user request
        |
        v
17A application flow
        |
        +--> request_id
        |
        v
validated Markdown mutations
        |
        v
17C Git history adapter
        |
        `--> one local commit for the logical request
             Odyssey-Request: <request_id>
```

Markdown remains authoritative. SQLite indexes, embeddings, Git metadata, and any future remote repository remain derived/supporting infrastructure.

## Responsibility boundary

Per-note functions such as `materialize_create()` and `materialize_update()` must not know that Git exists. They continue to validate and persist Markdown through the established Core boundaries.

Phase 17C belongs at the application boundary because the application already knows when one logical request starts, which independent writes succeeded or failed, and when the request-level mutation attempt is complete.

Conceptually:

```text
materialize_create/update/delete/migrate
        |
        `--> Markdown only

17A request executor
        |
        +--> execute bounded mutations
        +--> collect success / failure evidence
        `--> return request_id + affected IDs

17C history adapter
        |
        `--> commit successful request-level Markdown changes
```

## Initial commit granularity

Prefer **one Git commit per logical user request**, not one commit per note.

This aligns version history with user intent and makes bulk or multi-note changes easy to inspect and potentially revert as one logical operation.

Examples:

```text
"Marta ahora vive en Lyon"
    -> one request_id
    -> one note changed
    -> one local commit

"Añade review a todas las personas nacidas en 1990"
    -> one request_id
    -> N notes changed
    -> one local commit containing those N note diffs
```

If a request has partial success, already-valid independent writes are not rolled back merely to produce an all-or-nothing Git commit. The commit contains the successful Markdown changes; Phase 17B pending-work state records failed or deferred operations separately using the same `request_id`.

## Request correlation

Use the stable `request_id` created in Phase 17A. Do not invent a second Git-specific request identifier.

Prefer a commit trailer or equivalent safe metadata such as:

```text
Odyssey-Request: <request_id>
```

Future semantic request history, if implemented after E2E evidence, should correlate to Git through this same `request_id`. Do not require a request-history record contained in a commit to store that same commit's final SHA because the SHA depends on the committed tree and would create a circular self-reference.

## Benefits

The intended value is to obtain, with little new domain machinery:

- human-readable diffs for note updates;
- file and vault history;
- auditability of what one Odyssey request changed;
- recovery from accidental or bad mutations;
- request-level inspection of bulk changes;
- a future path to safe revert tooling;
- optional off-device backup/synchronization through a private Git remote later.

Git history may support later HITL/review UX by presenting request-level diffs, but Git itself must not become the HITL workflow engine.

## Initial scope

Phase 17C should start with a **local Git repository only** and the smallest adapter needed to detect request-level Markdown changes and commit them safely.

A remote repository, automatic push/pull, conflict resolution across devices, credentials, encryption, retention policy, and backup-provider choice are separate operational/security decisions. Do not add them merely because local history uses Git.

## Safety and semantics

- Git does not replace Odyssey revision guards or schema validation.
- Git does not authorize writes, resolve identities, or define note lifecycle semantics.
- Soft delete remains canonical Markdown state such as `deleted: true`; Git history is additional recovery evidence, not the delete contract.
- A Git revert must not be exposed as a generic production mutation until Odyssey has a safe application-level contract for reconciling revision/index state after restoration.
- Git commands must not operate on unrelated files outside the configured vault repository.
- Commit metadata should preserve `request_id` without storing secrets or unnecessary raw user content in commit messages.
- Per-note materializers remain unaware of Git.

## Out of scope

- making Git the canonical database;
- committing inside every persistence primitive;
- one commit per note by default;
- automatic remote push/pull;
- multi-device merge/conflict handling;
- replacing soft delete with physical file deletion because Git can restore it;
- using Git rollback as a substitute for Phase 17B pending-work semantics;
- exposing unrestricted Git commands through the application boundary;
- semantic request-history representation;
- full operational tracing.

## Open decisions for Phase 17C

Before implementation, decide the smallest safe details from actual 17A application-flow evidence:

1. exact adapter/API shape;
2. how the application identifies the set of vault changes belonging to one request;
3. final commit-message format beyond the required `Odyssey-Request: <request_id>` correlation;
4. behavior when no canonical Markdown changed;
5. behavior when the vault already contains unrelated/uncommitted user edits;
6. whether request-level automatic commits should be default or configurable;
7. how later restore/revert operations revalidate schema, indexes, revisions, and application state.

Do not solve remote backup or multi-device synchronization as part of Phase 17C.
