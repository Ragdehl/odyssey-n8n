# Odyssey Agent Team — Pilot (18 Oct 2026)

A supervised, bounded **development workflow**, not a new Odyssey user-facing App or alternate Core, Writer, Graph or database.

## Owner and roles

Supervisor: `scripts/odyssey_agent_cycle.py` is a deterministic state machine that checks gates, records status/receipts, bounds attempts and protects DEV/PROD. Five Codex specialists run *one at a time* in a fresh `agent/<job>` Git worktree:
1. Builder — implementation and focused tests when Codex is the primary developer, or repairs after independently reviewing a change authored by ChatGPT (only editing specialist during the agent cycle).
2. Generality — reusable Core contracts, arbitrary future App audit.
3. Quality — security, E2/E3, canonical Writer, maintainability.
4. Testing — adversarial, full-source and genuine end-to-end evidence.
5. Performance — timed real Pi runs, RAM/CPU/swap and scaling evidence.

Reviewers are independent sessions with read-only sandbox and strict machine-readable results. The Builder receives all their findings and, if no essential environmental gate blocks work, may repair and repeat. Never more than three iterations or one Codex process concurrently.

## Status and commands (on the Raspberry Pi)

```bash
cd /home/ragdehl/projects/odyssey-e3-mutation
python3 scripts/odyssey_agent_cycle.py doctor
python3 scripts/odyssey_agent_cycle.py plan --spec ops/agent-team/pilot-p4.md --job p4-agents-pilot-20261018
python3 scripts/odyssey_agent_cycle.py status --job p4-agents-pilot-20261018
# To independently review a feature already written by ChatGPT in a clean, committed branch:
# BASE=$(git rev-parse <parent-commit>); TIP=$(git rev-parse HEAD)
# python3 scripts/odyssey_agent_cycle.py plan --spec ops/agent-team/pilot-source-overlap.md --job unique-job --implemented-by chatgpt --against "$BASE"
# python3 scripts/odyssey_agent_cycle.py run --job unique-job --max-rounds 1 --live
# Do NOT execute unsupervised until sandbox and real browser gate are evaluated:
python3 scripts/odyssey_agent_cycle.py run --job p4-agents-pilot-20261018 --max-rounds 2 --live
python3 scripts/odyssey_agent_cycle.py stop --job p4-agents-pilot-20261018
```

The `plan` operation is a **safe dry run**: it saves the brief and Git baseline but launches no Codex session and creates no extra worktree. `run --live` is explicit and creates a new local Git branch/worktree. The persistent report is `../.odyssey-agent-runs/<job>/status.json` with each round's logs and reviewer JSON (0700 directory). While running, the supervisor checks a STOP marker and real `/proc/meminfo` every two seconds; memory under 650 MiB cancels the Codex process. Time limit 20 minutes per specialist, maximum three repair cycles, test gate timeout four minutes each. On restart, the same job cannot be launched again silently. There is no auto-merge, auto-push or deployment.

The full offline gate is `scripts/odyssey_cross_surface_gate.py`, plus accepted-contract ledger and Ruff checks, and two independent model-sensitive E2/E3/QA and performance audits. **Offline green does not mean DEV-user-ready.** Even with all reviewers passing, it reports `reviewed_browser_gate_pending` until a real authenticated browser→n8n→GPT→Writer→Markdown→browser gate is integrated. A reviewer with missing necessary evidence returns `blocked`, stopping the repair loop instead of wasting further tokens.

## Current pilot boundaries

- Local model sessions run under the user's existing ChatGPT Codex login. CLI is `0.162.1`, Pi ARM64 4 GiB, 2 GiB swap. The supervisor ignores local Codex MCP configuration, filters environment secrets, restricts edits to an isolated workspace sandbox, and does not expose DEV/PROD volumes deliberately.
- **Not a formal OS/container isolation boundary.** The same Linux account owns personal files and credentials. For wholly unattended agents with arbitrary shell access, move the runner to a dedicated restricted account/container with no mount of `/data/odyssey`, Cloudflare tunnel credentials or deploy permissions. Do not interpret prompt prohibitions as security controls.
- The real-browser automated runner and mobile push notification channel are not connected yet. Codex on ChatGPT mobile supports remote/cloud task control, but Raspberry Pi host availability and the requested notification UX must be verified on this actual host. A local JSON report does not automatically message this chat. Options: Codex Remote, GitHub PR checks/notifications, or a separate read-only n8n notification bridge, subject to user preferences.
- No generic user-created App is executed untrusted here. Odyssey's eventual Lego/contracts model requires declarative capabilities, schema validation, data permissions, compositional contract tests, and isolated evaluation of generated Apps; running user-provided code with normal Core privileges would not be safe. We do not redesign E1–E6 while delivering this pilot.
- P4 currently has historical frozen benchmark failures: the full suite is NOT a green release gate unless only independently documented historical cases fail. Never update price hashes merely to greenwash the run.

## Next adoption gate

Pilot with ONE bounded, READ-ONLY architecture/generalization review. Verify actual Codex CLI JSON output, cancellation, Git worktree isolation, and resource reporting. Then run a tiny expendable feature through implementer→reviewers on a dedicated worktree. Integrate browser E2E and notifications before running substantial unattended loops. **Do not start the complete live loop without these proofs.**

## ChatGPT as the developer (same QA pipeline)

If ChatGPT produces code through the authorized remote session, commit that code on a feature branch after deterministic focused tests. Create a **new** job with `plan --implemented-by chatgpt --against <full-parent-SHA>`. The supervisor requires a clean committed source snapshot, verifies the comparison SHA is a genuine ancestor with a nonempty diff, pins the feature commit, and creates the same isolated audit worktree. On the first round the Builder role is SKIPPED, conserving Codex quota; all deterministic gates and independent reviewers still run. If a review FAILS on a repairable issue, the Builder gets the findings and works in that same isolated worktree on the next round. If the test/browser gate is blocked, it must not call Builder pointlessly. Never claim model review is equivalent to live user UI E2E.

For first pilot use `--max-rounds 1`: independent read-only audits **only**. A later unattended repair cycle requires separately verified OS/container isolation from personal vaults, credentials, tunnel and deployment rights. `status` never triggers models, and the chat may inspect the persistent report when asked. No automatic messages to this conversation are implied.

### Failure classification

Review JSON contains finding `actionability` (mandatory): `repairable` for bounded code/test changes versus `external` for credentials, authenticated browser/deploy approvals or evidence the runner cannot safely obtain. The supervisor runs another Builder round only for genuinely repairable blocking findings or failed deterministic gates, even if the same review also contains an external blocker. External-only findings halt without wasting an implementation cycle. A blocked `run` exits nonzero and never implies user-ready product acceptance. Tests: `tests/runtime/test_agent_cycle_supervisor.py`.


## Model routing and reported-token cap (18 October 2026)

The supervisor now uses **the project's audited, deterministic policy**, not another LLM deciding which LLM to call. See `ops/agent-team/model-policy.json` and `select_agent_model()`:
- **Economy:** `gpt-6-luna` / low effort for small scoped changes, log reading and ordinary validation.
- **Higher impact:** `gpt-6-sol` / medium when Core, runtime, app capability contracts, workflows or product UI code are changed, or the feature was declared `--risk high`. Roles generality, quality, testing and builder escalate; performance stays Luna unless a separate critical analysis is needed.
- **Critical/repeated architectural repair:** `gpt-6-sol` / high for explicitly critical work or a builder retry on a high-impact change.
- Both `gpt-6-luna` and `gpt-6-sol` were checked on the actual Pi via Codex CLI 0.162.1, with the expected model echoed by the runtime. No silent model substitution is allowed.
- Default **110,000 cumulative Codex-CLI-reported tokens per feature**, configured via `plan --token-budget N` (bounded 20,000–300,000). The initial cap is less than half the observed 249,201 reported tokens of the previous five-agent pilot. The cumulative count is persisted per model/role/round and checked before starting the next agent. One currently running Codex call cannot be preempted at an exact reported-token boundary: accounting is finalized after the CLI exits. It can exceed the remaining budget, at which point the supervisor blocks before the next session. Runtime time/memory and STOP limits still apply during each session. **Reported CLI tokens are NOT directly billing, credits or unique uncached input tokens.**
- `python3 scripts/odyssey_agent_cycle.py route --job <job>` predicts model tiers, reasons, changed-file count, and remaining budget using ZERO model sessions. Previous historical jobs without token telemetry display `used_reported_tokens: null`, not a fictitious zero.
- `plan --risk normal|high|critical` allows manual/ChatGPT impact declaration. In addition, the supervisor promotes reviews automatically if real touched paths include Core, runtime, Apps, workflow or product UI. When a Builder runs before a file exists, the initial model derives from the declared risk, and subsequent audits are upgraded using the actual changed paths. For uncertain P4/identity/Writer work, deliberately declare `--risk high` or `critical`; not every architectural concern can be inferred from filenames.

Avoid duplicate full-suite testing inside the Codex sandbox: it cannot open local sockets and creates false failures. Codex Builder runs **focused** tests only; the supervisor runs one authoritative cross-surface suite per repair round outside the model sandbox. Reviewers read the Git diff and relevant active contracts before opening unrelated repository history. All requirements in AGENTS.md remain in force, with no abbreviated permission checks.

This is the first functional cost-routing implementation, proven by 54 deterministic tests and tiny genuine Luna/Sol CLI availability probes. We have **NOT yet demonstrated** that the same P4 feature costs fewer credits end-to-end or that the developer and reviewers maintain equal or better quality on Luna. Next controlled A/B pilot must compare usage, elapsed time, hallucinated regressions and retained test coverage with the previous baseline before trusting the routing for large autonomous work.


### Empirical failed Luna pilot and next-session protection (18 October 2026)

**Actual experiment, not an estimate:** `agent-model-usage-pilot` (new CLI-only tooling acceptance profile) ran in a disposable isolated worktree with `--risk normal --token-budget 110000`. Luna/low Builder reported **85,844 tokens**, and Luna/low architectural reviewer reported **47,779 tokens**, total **133,623 tokens**. The Builder's 3 newly added tests failed under the authoritative host gate (1,115 Python passed + 3 failed, JavaScript 174 passed, Ruff/ledger passed). The architecture auditor independently found an overly broad documentation path allowlist. The CLI correctly stopped and marked the feature **blocked**, NOT accepted; quality/QA/performance did not run. The 110k cap was crossed by an already running 47.8k session, demonstrating that the CLI provides only end-of-session accounting. The prior 249,201-token five-agent pilot completed successfully, so the two outcomes cannot be compared as equally successful deliverables or treated as proof Luna saves money. See `docs/architecture/agent-team-pilot-20261018.md` for full evidence.

**Corrective supervisor change:** A failed deterministic gate now bypasses ALL expensive reviewers. If a repair attempt and enough token headroom remain, the Builder receives the failing gate receipts in the next round. Otherwise it stops in `blocked_repair_budget` or `blocked_insufficient_token_headroom` without model calls. Before each session the supervisor requires at least 40,000 reported-token headroom (derived from these observed reviewer costs), preventing the specific avoidable overrun pattern. This is a conservative **preflight reserve**, not an exact maximum: individual agents can still consume more than their remaining budget while running. The policy cannot guarantee a strict budget until a supported live consumption stream/cancellation method is in place. Tests simulate failing gates, no reviewer launched, a budget-short repair blocked, and a successful second Builder iteration.


## Acceptance profile for internal tooling versus Odyssey product

For changes to the development supervisor only, `plan --acceptance tooling` can be used. The default `--acceptance product` NEVER changes: passing offline tests/reviewers still requires authenticated browser→n8n→GPT→Writer verification before user-facing approval. Tooling readiness is recorded as `reviewed_tooling_ready` only after passing all configured deterministic gates and independent AI reviewers, plus a closed allowlist of changed paths. A known/unknown Odyssey product source path, app implementation, workflow, untracked product file or unapproved doc blocks tooling readiness *before running gate or expensive reviewers*. `ready_for_user` on tooling means **ready for maintainer review of a CLI-only change**; it does NOT grant push/merge/deploy permissions.

The initial buggy tooling implementation was repaired separately by GPT-6 Luna and Sol on identical source+four failing tests. See `docs/architecture/agent-model-ab-20261018.md` for exact scorecard (Luna 31336 tokens / 43s, Sol 20494 tokens / 32s, both 64 focused PASS), and integration gate evidence. There is no reliable claim of lower actual money/credit cost. Avoid making a global model policy change based on one sample; the deterministic routing already promotes difficult repairs to Sol.


### Autonomous repair pilot outcome (18 Oct 2026)

The real `dirty-reviewer-autorepair-pilot` demonstrated a **failing host gate → unattended Sol medium repair → passing host gate**, followed by architecture and security independent PASS. The original run **blocked** before final Performance due to budget: builder 84995, generality 46055, quality 34196, QA 47693 = 212939 CLI-reported tokens out of 230000. QA incorrectly self-blocked because future reviewer results did not exist during its own turn. The testing role instructions now explicitly prevent this false blocker; the supervisor alone aggregates final review completion. The code repair (content hash of dirty tracked/untracked files instead of porcelain status) was reviewed and validated locally; snapshot p95 ~20ms on Pi dev worktree, outside Odyssey request path. See `docs/architecture/agent-autorepair-real-pilot-20261018.md`. The budget of 110k default is NOT proven sufficient for a complete five-role cycle. Do not advertise this as all-roles-PASS or as product acceptance.

## Adaptive reviewers and upfront budget reservation (18 October 2026)

The supervisor's review requirements now come from `model-policy.json`, validated against a **non-negotiable product baseline**. **All `product` changes (at any risk), and all `high` or `critical` tooling jobs, require four independent specialists**: Generality, Quality, Testing, Performance. No user-created app can declare a cheaper tooling acceptance profile to bypass this: the source-path allowlist will reject changes to Core, runtime, apps, UI, workflows or unrelated docs. For `tooling + normal` ONLY, Generality and Quality are independently mandatory and the authoritative cross-surface Python+JS tests, acceptance ledger and Ruff still run. Semantic QA/performance model reviewers are explicitly marked `omitted`, NEVER `pass`; optional human review remains possible, and high-risk tooling must declare high/critical.

Based on observed Pi usage, the initial minimum reported-token reserves are Generality 55k, Quality 45k, Testing 55k and Performance 50k, **plus 40k for a Codex Builder when one is required**. Before creating the worktree or launching a model, the supervisor refuses a job when the full selected reviewer set cannot fit its stated budget. After the deterministic gates, it checks the remaining review set again against actual Builder usage; before each reviewer it requires sufficient reserve for **ALL** reviewers still pending, not just the imminent one. Budgets and role selection are shown using `route --job ...` for FREE, and persisted as `review_plan` with required/deferred roles and explicit reasons. No accepted product job can omit specialists simply to match a cheaper budget. A **110k default budget CANNOT fund the full product review** and will block before the Builder; this is intentional, not a reason to increase the budget silently. An operator must knowingly plan a bigger product job budget (up to the existing hard max 300k) or narrower, safe iterations.

These reserves are minimum risk controls from previous observations, **not upper bounds, quotas, guarantees of money, or hard intrasesion token caps**. One model session may still overrun. Required reviews that are skipped because of insufficient reserve block the job `blocked_insufficient_review_budget` with `ready_for_user=false`, never become PASS. The review prompt includes the exact planned selection so the QA model cannot misinterpret its own in-progress status or falsely demand future unselected reviewer artifacts.

Cost comparison needs to compare the COMPLETE accepted outcome, not just tokens for a partial cycle. Product E2E browser→n8n→Writer remains independent of these policy changes.

### Automatic escalation for safety-sensitive supervisor changes

The policy also classifies **actual changed source paths** independently of the developer's risk label. Any edit to `scripts/odyssey_agent_cycle.py`, `ops/agent-team/model-policy.json`, the review output schema or specialist instruction files automatically upgrades a tooling job from `normal` to `high` and requires **all four** specialist agents and the corresponding 205k minimum review reserve. Both ChatGPT-originated changes and changes added by a Codex Builder are checked against the pinned Git baseline; a Builder that unexpectedly edits safety-sensitive files is reclassified **after implementation but before any auditor launch**. The default 110k budget will then block, never mark it approved with two agents. The effective risk, triggering paths and reviewer requirements are visible from the model-free `route --job` preview (ChatGPT/committed changes) and the persisted post-gate review quote.

This is important: `--risk normal` is a requested classification, NOT a security override. The policy requires the sensitive catalog to include the supervisor source file, model policy, result schema, and every specialist prompt; removing any of them invalidates the policy. Routine documentation within `ops/agent-team/` can still receive the narrower two-reviewer process; all Odyssey product changes retain four reviewers regardless of labels. The builder source can be expensive before the true changed paths are known, so correctly declaring high-risk up front is still advised; the post-builder guard closes the approval bypass but cannot refund tokens already spent.
