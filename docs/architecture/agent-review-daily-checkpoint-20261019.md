# Agent reviewer daily checkpoint — 19 October 2026 (branch only)

## Scope and evidence

Manual continuation at the independent-review boundary. `scripts/odyssey_agent_cycle.py` now recognizes a dedicated `DailyBudgetPause` raised **before** launching a reviewer, writes phase `paused_daily_budget`, saves the current round, required reviewer set, next role and SHA-256 of the complete bounded review snapshot. Successful Builder, deterministic gates and previous reviewer verdicts remain persisted.

Operator may invoke `python3 scripts/odyssey_agent_cycle.py resume --job JOB --live` **only after explicitly configuring a local reported-token pacing proxy** and sufficient next-day headroom. An exclusive supervisor lock still applies. Before running the next reviewer, the resume validator checks the exact saved worktree branch, full tracked/staged/untracked bytes, review order, required reviewers, all green deterministic gates and the saved JSON artifact for every finished review. Unfinished auditors retain their independent review and budget reservation. It does not rerun completed Builder/gates/auditors and cannot mark a product feature ready without the separate authenticated browser/n8n/model/Writer E2E.

`run --live` for new jobs remains independent; other blocked phases cannot be force-resumed. If the daily budget is exhausted before the initial Builder, the CLI refuses without creating a job execution, allowing a later ordinary start. Builder-stage or interrupted-in-flight sessions and completed jobs are deliberately NOT resumable. There is no scheduler, auto-next-day launch, notifications, provider quota readout, or intrasesion token cutoff. This does not fix the **separate per-job budget** shortfall of the earlier scoped-agent pilot, which requires a newly authorized job budget/review plan.

## Verification

Focused suite: `python -m pytest -q tests/runtime/test_agent_daily_review_resume.py tests/runtime/test_agent_cycle_supervisor.py tests/runtime/test_agent_daily_pacing.py`: 130 passed; Ruff lint/format: passed. No live model, DEV/PROD deploy, Git push, PR merge or Cloudflare change. The official provider-free cross-surface gate also passed: **1222 Python tests, 7 subtests, and 178 JavaScript tests**, exit 0. No independent four-auditor approval or runtime product acceptance is claimed.

## Pre-launch Builder extension (19 Oct 2026, same local feature branch)

A Builder model blocked by daily pacing **before it starts** may now checkpoint at stage `builder` in its existing isolated worktree. This includes the first round or a later repair round. The checkpoint binds the exact Git source snapshot, pinned current feature brief, selected independent review policy, total recorded tokens and prior-round review/gate findings. A later explicit `resume --job JOB --live` revalidates all those and its **remaining per-job reserve** before invoking Builder once; then reexecutes the deterministic gates and mandatory independent reviewers as usual. Completed earlier-round work is not replayed. Files changed by a partially executed Builder or a supposedly read-only reviewer cannot create a safe daily-pause checkpoint. Explicitly blocked/failed work and unknown in-flight processes are not eligible.

Proved using disposable real Git repos and mocked model calls. The new Builder tests exercise first-round pause, subsequent repair with preserved Generality FAIL findings, resumed build without repeat, seven stale/tampered states, partial Builder write refusal, and absent pacing policy. Existing reviewer tests add mutation-before-pausing refusal. All the above is **pre-launch checkpointing, not resuming an in-flight Codex process**, and uses a local *reported-token proxy*, not OpenAI account quota. No schedule/notification/autonomous nighttime execution has been enabled. The full official offline gate must pass before recording branch readiness.

### Read-only future budget quote

The `route --job JOB` dry-run now includes the full Builder + reviewer reserve if a Builder is paused, and lists **only remaining reviewers** when a reviewer is paused. Two additional tests check correct quoting (including the formerly underquoted Builder). This is an estimated CLI-reported-token capacity, never live ChatGPT account quota or a model bill.

## Verification of Builder extension and quote (19 October 2026)

Focused tests `test_agent_daily_builder_resume.py` + reviewer/pacing/supervisor: **144 passed**. Official provider-free regression gate: **1236 Python passed, seven subtests passed, 178 JavaScript passed (0 failed)**. Ruff lint/format, acceptance ledger, `git diff --check`: PASS. All fixtures synthetic, no live Codex usage. DEV and PROD health HTTP 200 before commit, no deploy, no merge and no push. Local operator proxy remains unconfigured and the older 220k job remains blocked by job-budget reserve, not automatically resumed.
