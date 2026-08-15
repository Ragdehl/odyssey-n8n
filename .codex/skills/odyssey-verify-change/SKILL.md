---
name: odyssey-verify-change
description: Run Odyssey's scope-aware quality gate before declaring work complete, marking a checkpoint complete, or finalizing or updating a pull request. Use for requests such as "verify this change" or "run Odyssey verification," and after implementation when completion claims need evidence.
---

# Odyssey Verify Change

Determine the changed scope first, then run the repository-defined checks that provide meaningful evidence for that scope. Fail clearly when a required check cannot run.

Run routine verification actions autonomously when they are reversible, isolated, and within the approved scope. Repeated test runs, n8n workflow executions, non-destructive probes, and disposable test fixtures do not require separate confirmation merely because verification needs several iterations. Follow `AGENTS.md` for the repository's authoritative safety boundaries.

## Workflow

1. Read `AGENTS.md`, repository test documentation, and validation scripts relevant to the changed files. Inspect the current branch, working tree, changed-file list, and full diff against the appropriate base.
2. Derive the verification matrix from the change:
   - during implementation, prefer the narrowest useful functional tests and validators for the changed scope;
   - discover commands from repository documentation and scripts instead of embedding a permanent exhaustive command list here;
   - before completion, require the repository's complete local deterministic gate.
3. Reuse trustworthy fresh evidence instead of blindly rerunning it:
   - evidence is fresh only when the command, result, scope, and current Git tree or commit are known from the current task;
   - reuse a successful complete local gate when no relevant tracked or untracked file has changed since it ran;
   - run any missing scope-specific check not covered by that evidence;
   - if relevant files changed, or freshness cannot be established, rerun the affected gate;
   - do not create a persistent cache, state file, database, or evidence service.
4. Run `git diff --check` against the intended change.
5. Run the repository's established secret-pattern scan. If no scan command is documented, use a high-confidence credential/private-key pattern scan that excludes `.git`; state the fallback used.
6. Review the changed-file list and full diff for correctness, unrelated edits, generated artifacts, credentials, and unintended architecture changes.
7. Check protected out-of-scope areas explicitly, especially `/data/odyssey`, Docker configuration, and n8n workflows unless the request placed an area in scope:
   - when a reliable before/after baseline exists, compare against it and report whether the area is verified unchanged;
   - otherwise inspect the operations performed during the current task and report whether any operation targeted the area;
   - when only task-action evidence exists, state that limitation and do not claim the external area is unchanged, because changes outside the observed task cannot be excluded.
   Never print secret values.
8. Confirm behavior or architecture documentation changed when needed. Do not mark completion before checks pass.
9. Confirm the final Git working-tree state and distinguish intentional uncommitted changes from unexpected files.
10. Return `PASS` only when every applicable required check ran or had trustworthy fresh evidence and passed. Otherwise return `FAIL`, name each failure, stale result, or skipped required check, and do not claim readiness. `FAIL` means not ready, not automatic rollback: preserve coherent, reviewable work on the feature branch and record failures or blockers in a checkpoint commit or Draft Pull Request when useful. Remove only disposable fixtures or probes, generated junk, secrets, unsafe changes, and clearly abandoned experiments.

## Report

Report PASS or FAIL, scope examined, commands/checks run or reused with results and evidence freshness, changed and protected-area findings with their evidence level, documentation accuracy, working-tree state, and blockers. Distinguish `verified unchanged`, `no task operation targeted the area`, and `unable to prove external state did not change`.
