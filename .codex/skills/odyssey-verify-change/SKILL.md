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

## Independent Codex audit timing

- **During implementation:** the author runs focused checks and can request one scoped, independent, read-only Codex review after a meaningful source slice. Findings are for repair; this is not a four-role final acceptance.
- **Every independent code review MUST inspect architectural reuse and coordinator lightness** using `ops/agent-team/{generality,quality,testing,performance}.md`: for every new/changed substantive function/logic, compare the active call path against matching existing/historical implementations, identify the canonical owner, and demand either reuse/consolidation or a documented separate security boundary. Reject duplicated Router/Temporal/Core/Writer/App logic or semantic `if` trees in the orchestrator, regardless of green tests. Reviewer JSON evidence must cite compared code paths, or the bounded search that found no equivalent. This is additive to, not a replacement for, source/actor/E3 correctness checks.
- **At a coherent integration checkpoint:** run full deterministic local/hosted CI, verify contracts and provenance, then schedule the existing supervisor's **four independent specialist roles** (Generality, Quality, Testing, Performance) on one pinned committed SHA and a short precise brief. The normal product acceptance policy already requires all four roles; use `ops/agent-team/README.md` and `scripts/odyssey_agent_cycle.py`. The supervisor plan/route/pace are read-only. Estimate and explicitly check the 4-role reserve and current pacing; the normal 110k budget is insufficient. Do **not** launch a costly or write-capable cycle blindly or without the relevant authorization.
- **Read-only audit evidence-size preflight:** before planning an agent handoff, compare the actual Git diff bytes for the chosen baseline against `scripts/odyssey_agent_cycle.py` `REVIEW_EVIDENCE_LIMIT` (currently 256 KiB). If oversized, do **not** launch and retry the same blocked job or blindly lift its limit: choose a truthful, small repair delta with verified prior review context, or explicitly plan a supported complete-review packaging solution. An incremental four-role result only covers its named diff; missing integrated-role approvals remain pending. This prevents oversized-diff modelless blocking loops without weakening the supervisor guard.
- **After substantive corrections:** rerun affected deterministic gates and independent review on the **new** SHA; earlier role PASS on old code is historical evidence, not approval of changes. An incremental review is appropriate when all previous four independent roles genuinely passed and changes are proven narrow. Fix actionable defects before another complete review; do not repeat full auditions in a loop to generate votes.
- **Full-source acceptance is input → physically read back output, not intermediate-shape matching.** The frozen 27+ cases define required user *meanings/actions*, not exact Router branch, number of intermediate facts, exact prose, or fixed note count. Every final test must invoke real models through the app and check canonical Markdown/Notes/Calendar/reload/replay; intermediates are diagnosed for unexpected refusal, missing units and wrong authority. Accept alternate safe interpretations only with an explicit semantic justification and independent review proving full coverage and no unsupported facts; ambiguity must be safely pending, not guessed. Keep deterministic offline gate for iterations, never as final substitute.
- **Phase acceptance is a hard gate, not a conversational impression.** Every completed R0–R4 architecture/LLM/semantic phase MUST pass `python scripts/odyssey_acceptance_contracts.py --require-stage-accepted Rn` for its own `Rn`, not merely the default offline integrity command. `docs/architecture/odyssey-phase-acceptance.json` is checked by the normal CI job for every PR; a non-draft PR or a push to dev touching Core/Apps/Runtime/web/workflows/config also runs `--require-review-stage-accepted` and is BLOCKED until the declared review stage is genuinely accepted; it marks each stage in progress until a case-by-case F01–F27 **plus every append-only R28+ regression** real-model + authenticated visible-browser→real n8n→Core/E3→physical Markdown→Notes/Calendar/reload/replay run and four fresh SHA-matched reviewer receipts exist. Absence, case omissions, stale code or mismatches mean `NOT ACCEPTED`. Do not mark a stage accepted in the roadmap, PR or assistant response when the required command fails. The gate checks receipt completeness and hashes; **it cannot prove a self-authored claim really came from a live provider/browser**. Independently inspect actual run provenance, trace and isolated actor/vault, then truthfully report exactly which user-action and model boundaries were witnessed. The original 27 are immutable, and each newly observed defect must add a durable, expected-behavior case to `tests/fixtures/odyssey_additional_regressions_v1.json` before repair; existing cases may not be removed or rewritten. Run the offline regression suite on every relevant change, then fresh model+browser for **every** current case before accepting each functional stage, without claiming that CI has provider access. Do not use the historic recorded 27-case replay or `pytest` as a substitute. Treat source changes after acceptance as requiring a fresh matching gate.
- **Before the PR is ready to merge:** require the four role receipts or clearly mark missing roles BLOCKED/NOT RUN, sufficient real-model evaluation for model-facing logic, and *real* deployed DEV user E2E for product adoption. CI PASS alone, Chromium with mocks, and four reviewer PASS alone do not imply product ready. Merge/deploy still require explicit authorization.
- On each progress report use `odyssey-results` to show the **named roles** and when the next audit will happen. Avoid reporting "audited" without actual fresh model receipts.

## Report

Report PASS or FAIL, scope examined, commands/checks run or reused with results and evidence freshness, changed and protected-area findings with their evidence level, documentation accuracy, working-tree state, and blockers. Distinguish `verified unchanged`, `no task operation targeted the area`, and `unable to prove external state did not change`.
