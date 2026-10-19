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
