# Phase 17 Git vault history direction

Status: **planned Phase 17 application-boundary capability; not implemented**

## Objective

Use Git as an optional history, diff, audit, and recovery layer around Odyssey's authoritative Markdown vault without making Git the source of truth or coupling per-note domain materialization to version-control commands.

```text
logical user request
        |
        v
Phase 17 application flow
        |
        v
validated Markdown mutations
        |
        v
Git history adapter
        |
        `--> one commit for the logical request
```

Markdown remains authoritative. SQLite indexes, embeddings, Git metadata, and any future remote repository remain derived/supporting infrastructure.

## Responsibility boundary

Per-note functions such as `materialize_create()` and `materialize_update()` must not know that Git exists. They continue to validate and persist Markdown through the established Core boundaries.

Phase 17 is the natural owner because it knows when one logical request starts, which independent writes succeeded or failed, and when the request-level mutation attempt is complete.

Conceptually:

```text
materialize_create/update
        |
        `--> Markdown only

Phase 17 request executor
        |
        +--> execute one or more bounded mutations
        +--> collect success / failure evidence
        `--> history adapter commits successful request-level changes
```

## Initial commit granularity

Prefer **one Git commit per logical user request**, not one commit per note.

This aligns version history with user intent and makes bulk or multi-note changes easy to inspect and potentially revert as one logical operation.

Examples:

```text
"Marta ahora vive en Lyon"
    -> one request
    -> one note changed
    -> one commit

"Añade review a todas las personas nacidas en 1990"
    -> one request
    -> N notes changed
    -> one commit containing those N note diffs
```

If a request has partial success, already-valid independent writes are not rolled back merely to produce an all-or-nothing Git commit. The commit contains the successful Markdown changes; Phase 17 pending-work state records failed or deferred operations separately.

## Relationship with semantic request records

Phase 17 also plans one queryable Markdown `user_request` record per logical Odyssey request. That record preserves the user request, validated plan, execution outcome, and affected stable IDs while remaining excluded from ordinary knowledge retrieval by default. See [Phase 17 semantic request records](phase-17-request-records.md).

Correlate the semantic record and Git history using a shared stable `request_id`. Do not require the request record contained in a commit to store that same commit's final SHA because the SHA depends on the committed tree and would create a circular self-reference.

Prefer a commit trailer or equivalent safe metadata such as:

```text
Odyssey-Request: <request_id>
```

## Benefits

The intended value is to obtain, with little new domain machinery:

- human-readable diffs for note updates;
- file and vault history;
- auditability of what one Odyssey request changed;
- recovery from accidental or bad mutations;
- request-level inspection of bulk changes;
- a future path to safe revert tooling;
- optional off-device backup/synchronization through a private Git remote.

Git history may support later HITL/review UX by presenting request-level diffs, but Git itself must not become the HITL workflow engine.

## Initial scope

Phase 17 should first consider a **local Git repository only** and the smallest adapter needed to detect request-level Markdown changes and commit them safely.

A remote repository, automatic push/pull, conflict resolution across devices, credentials, encryption, retention policy, and backup-provider choice are separate operational/security decisions. Do not add them merely because local history uses Git.

## Safety and semantics

- Git does not replace Odyssey revision guards or schema validation.
- Git does not authorize writes, resolve identities, or define note lifecycle semantics.
- Soft-delete behavior remains canonical Markdown state such as the future `deleted: true`; Git history is additional recovery evidence, not the delete contract.
- A Git revert must not be exposed as a generic production mutation until Odyssey has a safe application-level contract for reconciling revision/index state after restoration.
- Git commands must not operate on unrelated files outside the configured vault repository.
- Commit metadata should preserve a safe request/trace correlation identifier when Phase 17 tracing exists, without storing secrets or unnecessary raw user content in commit messages.

## Out of scope

- making Git the canonical database;
- committing inside every persistence primitive;
- one commit per note by default;
- automatic remote push/pull;
- multi-device merge/conflict handling;
- replacing soft delete with physical file deletion because Git can restore it;
- using Git rollback as a substitute for Phase 17 partial-success and pending-work semantics;
- exposing unrestricted Git commands through the application boundary.

## Open decisions for the Phase 17 contract

Before implementation, decide the smallest safe details from actual application-flow evidence:

1. exact adapter/API shape;
2. how the application identifies the set of vault changes belonging to one request;
3. commit-message format and trace/request correlation;
4. behavior when no Markdown changed apart from a possible `user_request` history record;
5. behavior when the vault already contains unrelated/uncommitted user edits;
6. whether request-level automatic commits should be default or configurable;
7. how later restore/revert operations revalidate schema, indexes, revisions, and application state.

Do not solve remote backup or multi-device synchronization as part of this initial Phase 17 history capability.
