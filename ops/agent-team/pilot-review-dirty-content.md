# Bounded autonomous repair pilot: read-only reviewer content integrity

## Goal
Demonstrate without intermediate human confirmation the supervisor's actual control flow: ChatGPT-authored failing regression → deterministic full test gate FAIL in round 1 → **NO AI reviewer in round 1** → Codex Builder repairs generic supervisor logic in round 2 → gate reruns → independent architecture, quality, QA and performance reviewer decisions. Report exact model/usage per session. We are NOT testing the Odyssey application or changing DEV/PROD.

## Confirmed existing defect (first round must fail)
`scripts/odyssey_agent_cycle.py:run` protects read-only reviewer integrity by checking before/after `git status --porcelain` only. When a tracked file was already modified, an AI reviewer may change its contents while its porcelain line is unchanged (` M existing.py`); the supervisor accepts the reviewer as read-only. A NEW committed adversarial test `test_dirty_tracked_file_mutation_by_readonly_reviewer_is_detected_even_when_git_status_matches` reproduces this defect in its own temporary Git repo. It is intentionally RED in the handoff commit: `reviewed_browser_gate_pending` instead of required `blocked`.

## Contract for Builder and reviewers
- Implement generic, efficient snapshot protection of file *content* before and after each reviewer. Include tracked staged and unstaged diffs AND untracked files; untracked file contents must be included, because creating/mutating an untracked file with the same path listing is still a mutation. Consider full `git diff HEAD --binary --no-ext-diff` plus secure, bounded deterministic content hashing of untracked files (without reading private paths). Do not silently omit files above size limit; if snapshot cannot be established, fail closed. No reliance on just porcelain/status filenames. Detect deletion/addition/renaming or file mode edits too.
- If reviewer causes any repository content mutation, stop immediately, preserve status `blocked` / `ready_for_user=false`, do not accept another independent reviewer, and do NOT write product data.
- Preserve Codex, ChatGPT, and independent reviewer pipelines and running time limits. Avoid heavy work on Odyssey's normal critical path: this is a dev-tooling-only guard. Keep one active Codex at a time; never increase token budgets.
- Add/extend generic regressions for dirty tracked files and untracked files mutating with unchanged paths. Do not weaken the committed RED test.
- The bounded acceptance profile here is `tooling`, never `product`; finish in `reviewed_tooling_ready` only if **all** Python+JS gates and four independent specialist judgments actually pass. A blocked/uncertain reviewer is not an approval.
- Do not run global cross-surface suite inside Codex sandbox (the supervisor runs it outside). Run just focused pytest and Ruff if available. Source files permitted: `scripts/odyssey_agent_cycle.py`, `tests/runtime/test_agent_cycle_supervisor.py`, and this spec/agent-team docs. Do not change acceptance ledger or benchmark thresholds.

## Safety
Only local disposable Git worktrees and synthetic notes. NO DEV/PROD deploy, user vaults, credentials, network routes, remote pushes, public services or privileged host operations. Preserve proven AGENTS.md, application extensibility contracts, E2/E3 and browser acceptance requirements. Never claim an app/UI E2E has passed. Actual Codex CLI use is capped by planned token budget and time limits.
