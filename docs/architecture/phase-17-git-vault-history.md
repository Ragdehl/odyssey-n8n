# Phase 17C local Git vault history

Status: **contract refined; implementation not started**

## Objective

Use Git as an optional history, diff, audit, and recovery layer around Odyssey's authoritative Markdown vault without making Git the source of truth or coupling per-note domain materialization to version-control commands.

Phase 17A introduces one stable `request_id` for each logical Odyssey request. Phase 17C reuses that same identifier to correlate request-level Markdown changes with local Git history.

```text
logical user request
        |
        v
validated RequestPlan
        |
        v
17C history begin snapshot
        |
        v
17A application flow
        |
        +--> request_id
        +--> successful affected stable IDs
        |
        v
17C safe path attribution
        |
        v
stage exact changed Markdown paths
        |
        `--> one local commit for the logical request
             Odyssey-Request: <request_id>
```

Markdown remains authoritative. SQLite indexes, embeddings, Git metadata, and any future remote repository remain derived/supporting infrastructure.

## Architecture-challenge conclusion

Phase 17C should remain a small **request-boundary adapter**, not a generic version-control subsystem.

The important safety problem is attribution: Odyssey must not create a request commit containing unrelated manual edits merely because they happened to be present in the same vault. The smallest useful design is therefore:

1. take a non-mutating Git working-tree snapshot after a valid plan exists and before Odyssey writes;
2. execute the normal request without changing per-note materializers;
3. use the request's successful `affected_stable_note_ids` to resolve the exact canonical Markdown paths Odyssey touched;
4. reject automatic history attribution if any of those paths was already dirty before the request;
5. stage only those exact request paths, never `git add .`;
6. create one local commit if the staged diff is non-empty.

Unrelated dirty files are allowed and remain untouched.

```text
before request
  user-edit.md      dirty
  Marta.md          clean

Odyssey updates Marta
        |
        v
stage Marta.md only
        |
        v
commit request

user-edit.md remains dirty and uncommitted
```

If `Marta.md` itself was already dirty before the request, Odyssey performs the valid Markdown mutation but skips the automatic request commit because the resulting file cannot be attributed safely to Odyssey alone.

## Responsibility boundary

Per-note functions such as `materialize_create()`, `materialize_update()`, soft delete, type migration, and deterministic bulk update must not know that Git exists. They continue to validate and persist Markdown through the established Core boundaries.

Phase 17C belongs at the application boundary because the application already knows when one logical request starts, which independent writes succeeded or failed, and when the request-level mutation attempt is complete.

Conceptually:

```text
materializers / persistence
        |
        `--> Markdown only

execute_request()
        |
        +--> validated plan
        +--> history begin snapshot
        +--> execute bounded mutations
        +--> collect successful affected IDs
        +--> finalize Git history
        `--> return typed application + history evidence
```

History failure never grants, denies, or changes domain mutation authority.

## Git repository boundary

The Git repository root for Phase 17C is the **configured canonical vault root itself**, not `/data/odyssey` and not the application source-code repository.

For the current deployment shape that means conceptually:

```text
/data/odyssey/
├── vault/          <-- separate Git repository for canonical Markdown
├── config/
├── state/pending/  <-- never part of vault Git history
└── runtime/        <-- never part of vault Git history
```

This keeps durable workflow state and derived/runtime data outside canonical knowledge history.

A production `GitHistoryRecorder` must verify that `git rev-parse --show-toplevel` resolves to exactly the configured vault root. A parent Git repository is not acceptable: Phase 17C must never accidentally stage files outside the vault boundary.

Git initialization/bootstrap is **explicit operational setup**, not an implicit side effect of `execute_request()`. Enabling history requires an existing local vault Git repository with a baseline commit. Initializing a real user vault and creating that baseline may expose personal Markdown to Git history, so that setup remains an explicit user/deployment action rather than hidden application behavior.

Phase 17C does not configure or require a remote.

## Request-scoped adapter contract

The exact class names may vary during implementation, but the boundary should preserve this shape:

```text
valid RequestPlan
      |
      v
history.begin(request_id)
      |
      `--> snapshot of dirty/untracked paths at request start

execute Odyssey request actions
      |
      v
history.record(
    request_id,
    snapshot,
    affected_stable_note_ids,
    repository,
    schema,
)
      |
      `--> typed history outcome
```

`begin()` must not stage, commit, initialize a repository, or alter user files. It captures only the state needed for later safe attribution.

`record()` may resolve successful stable IDs to current validated canonical note paths, stage those exact paths, and commit them if safe.

The application must call `begin()` only after planning has produced a valid `RequestPlan` and immediately before any request mutation. A planning/provider failure therefore creates no Git activity.

History recording is optional by dependency injection/configuration. No injected recorder means Git history is disabled; Core does not need a second global feature flag.

## Typed history result

`ApplicationResult` should expose bounded history evidence separately from Phase 17B pending-work evidence.

The final representation may use a dataclass plus enum, but callers must be able to distinguish at least:

```text
DISABLED        no history recorder configured
NO_CHANGES      recorder enabled but no canonical Markdown diff resulted
COMMITTED       one request commit was created
SKIPPED_UNSAFE  request paths could not be attributed safely
FAILED          Git inspection/staging/commit failed operationally
```

A committed result includes the local commit SHA. Errors/reasons must be bounded and must not contain raw user requests or secrets.

History failure or unsafe attribution **does not roll back already-valid Markdown writes**. Phase 17B pending work continues to describe incomplete knowledge/application work; Git-history failure is separate operational evidence and must not be converted into semantic pending work.

## Initial commit granularity

Use **one Git commit per logical user request**, not one commit per note.

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

If a request has partial success, already-valid independent writes are not rolled back merely to produce an all-or-nothing application result. If every successfully affected path can be attributed safely, the Git commit contains those successful Markdown changes; Phase 17B pending-work state records failed or deferred knowledge operations separately using the same `request_id`.

If even one successfully affected path was dirty before the request, the initial Phase 17C policy is conservative: skip the **whole automatic request commit** rather than create a request commit that silently omits part of the successful mutation set.

## Identifying request paths safely

`ApplicationResult.affected_stable_note_ids` already provides the stable IDs from successful single and bulk write units. Phase 17C should reuse that evidence rather than infer request ownership from every file that happens to be dirty after execution.

After execution, the history adapter resolves those IDs against validated canonical Markdown and obtains the exact current vault-relative paths.

This works for the initial mutation set because:

- CREATE leaves the new stable ID in a new Markdown path;
- UPDATE preserves stable identity/path;
- soft DELETE preserves the Markdown file and stable ID;
- type migration preserves stable identity/path;
- bulk UPDATE already reports successful stable IDs.

A successful persistence operation may still be `NO_CHANGE`. Therefore affected IDs alone do not prove a Git diff exists. The adapter stages the safe exact paths and returns `NO_CHANGES` when the staged diff is empty.

Duplicate/ambiguous stable IDs, malformed canonical Markdown encountered during attribution, or an affected ID that cannot be resolved fail history recording explicitly rather than broadening the staged set.

## Dirty-vault policy

At `begin()`, capture Git status including tracked modifications and untracked paths relative to the exact vault root.

At `record()`:

```text
affected paths ∩ pre-request dirty paths
        |
        +--> empty
        |      stage exact affected paths
        |      commit if diff exists
        |
        `--> non-empty
               SKIPPED_UNSAFE
               no automatic commit
```

Unrelated pre-existing dirty files are not an error and are never staged.

The adapter must not use broad commands such as `git add .`, `git add -A`, or a repository-wide commit shortcut.

## Commit metadata

Use a neutral fixed subject plus the request correlation trailer:

```text
odyssey: apply request

Odyssey-Request: <request_id>
```

Do not place raw user requests, note contents, secrets, inferred personal information, model reasoning, or pending-work payloads in commit metadata.

The local adapter may use a fixed non-secret Odyssey Git author identity or an explicit local repository identity so operation does not depend on a developer's global Git configuration. This does not imply a remote account or external identity.

## Git command safety

The implementation should use fixed argument-vector subprocess calls or an equivalently bounded Git library API. Do not interpolate user content into shell commands and do not use unrestricted shell execution.

Git operations are limited to the exact configured vault repository and the exact attributed Markdown paths.

Expected operation families are small:

```text
git rev-parse / status
Git path staging for exact files
git diff --cached
git commit
git rev-parse HEAD
```

No push, pull, reset, checkout, clean, revert, rebase, force operation, or branch manipulation belongs in the initial request recorder.

## Request correlation

Use the stable `request_id` created in Phase 17A. Do not invent a second Git-specific request identifier.

Future semantic request history, if implemented after E2E evidence, should correlate to Git through this same `request_id`. Do not require a request-history record contained in a commit to store that same commit's final SHA because the SHA depends on the committed tree and would create a circular self-reference.

## Failure semantics

Git is audit/history/recovery infrastructure, never the transaction owner for canonical knowledge.

Therefore:

- Git begin/record failure does not cancel a valid Odyssey write;
- Git commit failure does not roll back Markdown;
- a partial application request may still have a request commit for its safe successful writes;
- Phase 17B pending persistence and Phase 17C Git persistence are reported independently;
- a request with no canonical Markdown changes creates no empty commit.

A failed or skipped history attempt leaves any resulting working-tree changes available for inspection/manual recovery.

## Concurrency limitation

The initial Phase 17C contract does not introduce a filesystem lock or transaction framework around Obsidian/manual editors and Odyssey.

The pre-request dirty-path snapshot prevents known pre-existing edits from being silently attributed to Odyssey. It cannot perfectly separate a new external edit that races on the **same affected path after the snapshot** and before Git staging.

The first E2E should therefore run under the existing practical single-writer assumption around an Odyssey request. If real concurrent editing creates a concrete problem, Phase 19 may add serialization, content fingerprints, or another measured hardening mechanism. Do not build a generic locking/synchronization system into Phase 17C pre-emptively.

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

## Verification requirements

Deterministic tests should cover at least:

1. one clean single-note UPDATE creates one commit with the request trailer;
2. multi-note and partial-success requests produce one commit containing only successful affected Markdown paths;
3. unrelated dirty files remain untouched and uncommitted;
4. a pre-dirty affected path produces `SKIPPED_UNSAFE` and no commit;
5. a `NO_CHANGE` request produces no empty commit;
6. CREATE, UPDATE, soft DELETE, type migration, and bulk-success path attribution work;
7. an affected ID that cannot be mapped safely fails history explicitly;
8. Git commit failure is reported without rolling back Markdown;
9. Phase 17B pending status remains independent when both pending work and history are present;
10. a Git repository whose top-level root is above the configured vault is rejected;
11. commit metadata contains the request ID but not raw request/note content;
12. no remote Git operation is invoked.

No production LLM prompt, Structured Output contract, or semantic model behavior changes in Phase 17C, so live-model evidence is not required merely for this Git adapter. Normal deterministic verification remains required under `AGENTS.md`.

## Initial scope

Phase 17C includes only:

- one local Git repository rooted exactly at the configured vault;
- explicit pre-existing Git bootstrap/baseline as a deployment prerequisite;
- request-scoped begin/status snapshot;
- stable-ID-to-path attribution for successful mutations;
- exact-path staging;
- one local commit per safe logical request;
- typed application history evidence.

## Out of scope

- making Git the canonical database;
- automatic Git initialization inside `execute_request()`;
- committing inside every persistence primitive;
- one commit per note by default;
- automatic remote push/pull;
- multi-device merge/conflict handling;
- generic filesystem locking;
- replacing soft delete with physical file deletion because Git can restore it;
- using Git rollback as a substitute for Phase 17B pending-work semantics;
- exposing unrestricted Git commands through the application boundary;
- semantic request-history representation;
- full operational tracing;
- user-facing restore/revert.

## Deferred restore/revert contract

Git restoration remains intentionally out of scope. A later restore/revert operation must re-enter a safe Odyssey application boundary so schema, stable identity, revision/index state, and derived indexes can be reconciled. Direct unrestricted production `git revert`/`checkout` is not exposed as a user mutation in Phase 17C.

The governing rule is: **Git records successful canonical Markdown mutations; it never decides what knowledge is true or which write is allowed.**
