# Pilot of autonomous agent cycle, scoped Codex (19 October 2026)

## Objective and isolation

The user authorized a first unattended development/review cycle. We deliberately selected a small internal-tooling test change rather than product code or deployment:

- Brief: `ops/agent-team/pilot-scoped-launch-tests-20261019.md`
- Job: `agent-native-scope-autonomy-20261019`
- Base commit: `5ae3739`
- Separate branch: `agent/agent-native-scope-autonomy-20261019`
- Worktree: `/home/ragdehl/projects/odyssey-agent-work-agent-native-scope-autonomy-20261019`
- Max rounds: **2**, risk: normal, acceptance: tooling, budget: **220,000 Codex-CLI-reported tokens**, single model process at any given time.
- Permission policy: a **real native Codex sandbox preflight before every model**, reviewer read-only, builder worktree-write only, host home/DEV/PROD and network inaccessible to model-directed commands. No deploy, merge, push or Cloudflare changes.

For normal-risk tooling the model policy mandates Generality and Quality specialist reviewers. Testing and Performance model reviewers are explicitly OMITTED by policy; the full deterministic Python+JavaScript+Ruff+acceptance gate remains mandatory. Do not present this as all FOUR model specialists approving the feature, nor as product acceptance.

## Real progression — NOT an all-green accepted cycle

| Step | Outcome | CLI reported tokens |
|---|---|---:|
| Round 1 Builder, Luna low | Added focused security regressions to tests/runtime/test_agent_cycle_supervisor.py | 47,400 |
| Round 1 authoritative Python+JS/acceptance/Ruff gate | All PASS | 0 (deterministic) |
| Generality reviewer | PASS | 34,377 |
| Quality reviewer | FAIL (repairable, flawed interpretation) | 37,376 |
| Round 2 Builder repair | Added a focused optional timeout test | 34,678 |
| Round 2 authoritative Python+JS/acceptance/Ruff gate | All PASS | 0 (deterministic) |
| Round 2 mandatory independent reviews | BLOCKED BEFORE MODEL CALLS | 0 |

**Total:** 153,831 reported tokens over four Codex sessions. Budget 220,000, remaining 66,169. Both Generality+Quality reviewer reservations required 100,000 minimum, so the deterministic supervisor stopped with phase `blocked_insufficient_review_budget`, `ready_for_user=false`. Exit code from CLI run: **3**. No further model call was attempted and no automatic deployment happened.

Quality claimed the brief **required** testing `subprocess.TimeoutExpired` as a blocking acceptance criterion, despite the brief labeling it explicitly **optional**. It also reported pytest unavailable inside the read-only sandbox; that was a limitation of the model shell, not a failed authoritative host gate. Generality had approved the original round. The second Builder nevertheless added the optional regression and all tests passed, but the supervisor correctly required fresh independent approval and could not afford it.

The AI-produced test-only diff remains in its isolated agent worktree/branch, **not merged** into the principal Odyssey branch because mandatory round-2 model approvals did not complete. Inspect `../.odyssey-agent-runs/agent-native-scope-autonomy-20261019/status.json`, `round-1/generality.json`, `round-1/quality.json` and `round-2/*` for saved receipts. No private data is needed for the analysis.

## Improvements from this experiment (implemented separately by ChatGPT)

**Fixed premature repair spending:** Before **any round 2 or later**, the supervisor now calls the deterministic risk-aware `review_budget_quote(include_builder=True, dest=worktree)`. If there is not enough for the Builder's minimum headroom **AND the full mandatory review reserve**, it blocks before launching a model. In THIS actual case, after round 1 the balance would have been **100,847 tokens**, but minimum combined reservation **140,000**. The change would have saved **34,678 reported tokens**. This is an estimate based on measured round-2 use, not a guarantee of hard per-session limits.

**Fixed reviewers treating an optional wish as a blocker:** The central `instructions()` contract now says an explicitly OPTIONAL criterion can only be a warning, and that failed attempts to launch pytest inside the restricted Codex environment do not supersede the supervisor's authoritative host test receipt.

Added reproducible regression test with the exact usage and two-reviewer failure data, requiring that no second Builder starts or round-2 directory exists when budget is insufficient. Added a common reviewer-prompt invariant. Focused supervisor tests: **99 PASS**. Full cross-surface Python/JS suite must be run before committing (results below).

This is an observation-driven improvement to the EXISTING deterministic Codex supervisor, not a new custom agent platform. The user asked for autonomous, safe development without manual approval every 30 minutes; the first half succeeded, but this test has not yet proven a complete independently accepted multi-agent cycle. The next pilot should be a similarly scoped change with sufficient separately approved quota or a cost-optimized reviewer design that does not reduce required audits; product functionality still requires all four specialist reviews and a real browser/n8n/GPT E2E gate.

## Product safety

DEV remains deployed at `b0fc9b21`; its Cloudflare public route list is MATCH following the separately authorized presence.js routing fix. PROD is untouched. No new data were written to Odyssey, and the agent-generated work was not merged, pushed or deployed.


## Follow-up real pilot: resume-quote tests, 19 Oct 2026 (NOT autonomously approved)

Distinct bounded job `agent-resume-quote-pilot-20261019`, pinned parent branch commit `13a6c8f`, isolated branch `agent/agent-resume-quote-pilot-20261019`. Local daily pacing enabled for this operator at a **hypothetical 2,750,000 weekly CLI-reported-token PROXY**, 20% reserve, 314,285 reported tokens/day; the local proxy must NOT be portrayed as the actual ChatGPT Plus allowance. Pre-pilot local history already accounted for 153,831 reported tokens today. The user-supplied Codex screen at 14:48 Paris time showed 98% five-hour remaining and 96% weekly remaining, but was not polled again at model-session boundaries, so the true post-pilot account quota is unknown.

- Original Codex Builder Luna-low generated **exactly three** focused tests, changing ONLY `tests/runtime/test_agent_cycle_supervisor.py` in its isolated worktree. **34,285** reported tokens.
- Authoritative HOST gate after Builder: **1,239 Python passed, 7 additional subtests passed, 178 JavaScript passed**; independent Ruff and acceptance-ledger gates PASS. The restricted Codex sandbox lacked local pytest/ruff executables, but its report did not supersede those authoritative host results.
- Generality independent reviewer Luna-low **PASS / 32,373 tokens**, including source-specific evidence and no additional feature requests.
- Quality independent reviewer Luna-low **BLOCKED / 22,520 tokens**, claiming a read-only shell could not read the workspace, without describing a specific failed command or source defect. The job stopped correctly as `blocked_external_evidence`, exit code 3, `ready_for_user=false`.
- Zero-model targeted Linux native sandbox preflight of the **same worktree/profile** proved source/Git READ access available, workspace WRITE denied, private paths and network denied. Focused supervisor tests: **102 passed**. This makes the original Quality objection unsupported by the effective permissions, but **does not turn the original BLOCKED verdict into PASS**.
- A separately documented **independent, read-only Quality diagnostic** received a trusted host-supplied, complete pinned Git diff, exact production helper and successful gate receipts (no need for source-shell tools). It returned genuine **PASS / 23,615 tokens**, with unchanged worktree fingerprint; its artifact is in the private job folder `quality-diagnostic/result.json`. This is advisory evidence, **NOT part of the supervisor's original required automatic review set**, and its output has NOT been substituted for the blocked official result.

Total **112,793 Codex CLI-reported tokens** for this job (Builder 34,285 + Generality 32,373 + initial Quality 22,520 + diagnostic Quality 23,615). At the post-pilot inspection, local daily usage across all jobs was **266,624/314,285** with **47,661 reported tokens remaining**, and both DEV and PROD origin health endpoints returned HTTP 200. No Git push, merge, branch adoption or DEV/PROD deployment; no personal vault or real product writes. Generated tests remain uncommitted in the isolated agent branch and are NOT present on the primary feature branch.

**Smallest remaining technical closure for autonomous acceptance:** readonly auditors need a trusted, bounded, source-pinned diff/gate evidence path (or else a proven actual readable tool invocation), and a fail-closed mechanism to retry a specifically blocked review without repeating a completed Builder/gate/Generality or altering an original verdict. This must be tested before accepting the cycle automatically; do NOT add a separate scheduler/notification/controller or rerun the full expensive pilot simply to manufacture success. A product feature still separately requires four specialists and true authenticated browser→n8n→live model→Writer E2E.
