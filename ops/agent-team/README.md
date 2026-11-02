# Odyssey Agent Team — Pilot (18 Oct 2026)

A supervised, bounded **development workflow**, not a new Odyssey user-facing App or alternate Core, Writer, Graph or database.

## Owner and roles

Supervisor: `scripts/odyssey_agent_cycle.py` is a deterministic state machine that checks gates, records status/receipts, bounds attempts and protects DEV/PROD. Five Codex specialists run *one at a time* in a fresh `agent/<job>` Git worktree:
1. Builder — implementation and focused tests when Codex is the primary developer, or repairs after independently reviewing a change authored by ChatGPT (only editing specialist during the agent cycle).
2. Generality — reusable Core contracts, arbitrary future App audit.
3. Quality — security, E2/E3, canonical Writer, maintainability.
4. Testing — adversarial, full-source and genuine end-to-end evidence.
5. Performance — timed real Pi runs, RAM/CPU/swap and scaling evidence.

Reviewers are independent sessions with read-only sandbox and strict machine-readable results. **All four** reviewer role prompts require explicit reuse-first inspection of changed functions against existing/historical implementations plus thin-coordinator ownership; the JSON `evidence` must cite actual paths and concrete comparisons, and a newly duplicated semantic mechanism or coordinator-owned domain decision is a blocking repairable finding. An absent equivalent must be supported by a bounded search, not asserted. The supervisor must not treat a green suite as a substitute for this audit. The Builder receives all their findings and, if no essential environmental gate blocks work, may repair and repeat. Never more than three iterations or one Codex process concurrently.

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

### Offline Linux sandbox proof (19 Oct 2026)

Use `scripts/odyssey_agent_offline_sandbox.py --workspace /tmp/odyssey-agent-sandbox-<random> --smoke` to prove host filesystem and network denial with disposable fixtures. The Linux Bubblewrap sandbox intentionally lacks Codex authentication, /data, DEV/PROD mounts, home and network: tests can write only inside the explicitly mounted synthetic scratch. It runs under user/PID/network namespaces; four actual Linux tests under `tests/runtime/test_agent_offline_sandbox.py` are in the cross-surface gate. **Do not use this offline script to claim Codex model agents are isolated:** they require remote network/credentials and still need egress/credential brokerage. See `docs/architecture/agent-offline-isolation-and-dev-browser-20261019.md`.

### Read-only DEV Chromium gate (19 Oct 2026)

Use `scripts/odyssey_dev_browser_readonly.cjs` with locally cached Chromium and Puppeteer to run a **non-writing** mobile/desktop DOM + reload + Core-receipt regression against deployed DEV. It starts `scripts/odyssey_dev_readonly_proxy.mjs` on an ephemeral loopback port, with a **deny-by-default operation whitelist** in `scripts/odyssey_dev_readonly_contract.mjs`. It blocks all browser message/Task/notes mutations, returns synthetic presence without writing DEV, and closes itself after the test. The 4 Node contract tests `tests/odyssey_dev_readonly_proxy.test.mjs` are included in the official Python+Node gate and test 403 on real loopback. This is neither Cloudflare Access auth nor a live P4 model/Writer browser gate. Further details: `docs/architecture/dev-readonly-browser-proxy-20261019.md`.


### Genuine Chromium→Core Writer synthetic browser test (19 October 2026)

Run `LD_LIBRARY_PATH=/tmp/odyssey-p4-browser-deps/root/usr/lib/aarch64-linux-gnu python scripts/odyssey_browser_synthetic_p4.py --viewport mobile` and repeat with `desktop` on the authorized Pi. Each disposable fixture launches a real localhost HTTP runtime, serves Odyssey's unchanged branch frontend and opens Chromium; it exercises actual P4 Core/Writer Markdown, transcript persistence, Notes UI, graph and same-ID E3 replay. The provider uses `RecordedClient` (no GPT), and a small test-only HTTP adapter substitutes for n8n. It is **not** product E2E or deploy authorization; keep the genuine authenticated browser+n8n+live-model gate pending. The deterministic projection and fail-closed graph schema tests are in `tests/runtime/test_browser_synthetic_p4_contract.py` as part of the official offline gate. See `docs/architecture/p4-synthetic-chromium-writer-e2e-20261019.md`.

### Real n8n engine smoke in a no-network container (19 Oct 2026)

Opt-in command `python scripts/odyssey_n8n_isolated_projection.py --run`. Reads one pinned deployed DEV n8n Code-node artifact, starts with real recorded-model Core Writer output and runs that exact Code node **inside n8n 2.33.7 itself**, in a Docker container with no network, no secrets, no private vault mount, fresh throwaway n8n DB. Verifies original Core write receipts and notes set survive. Docker launch arguments + workflow scopes have seven independent offline regressions `tests/runtime/test_n8n_isolated_projection_contract.py` in official gate. Be careful: this is not the actual webhook, actual provider, or authenticated browser. Never describe as full product E2E; see `docs/architecture/p4-isolated-n8n-code-engine-20261019.md`.

### Real n8n HTTP Webhook without network, fixture only (19 October 2026)

`python scripts/odyssey_n8n_isolated_webhook.py --run` starts a disposable n8n Docker instance (offline SQLite, network none, read-only host mounts) and sends a real localhost HTTP request to a real published Webhook, with the identical deployed DEV Code node that projects Core Writer receipts. Genuine Writer Markdown is produced in a disposable vault with recorded model outputs BEFORE the webhook, not dynamically from n8n. The test explicitly rejects wrong request IDs/text with HTTP 403 and wrong method with 404; never infer success merely from HTTP 200 on a failed Code node. Offline contract tests included in cross-surface gate; Docker run opt-in. **Not a production browser+n8n+GPT acceptance test**. [Technical evidence](../../docs/architecture/p4-isolated-n8n-real-webhook-20261019.md).

### Actual dynamic n8n HTTP→P4 Writer proof (19 October 2026)

Opt-in: python scripts/odyssey_n8n_dynamic_webhook.py --run. This invokes the actual P4 Core Writer on demand FROM a real n8n HTTP Request, through a restricted Unix-domain socket to a disposable host-only test actor/vault. Docker network none, no DEV/PROD volumes or secrets. Repeated same-ID request must preserve all Markdown SHA256 hashes; wrong ID and wrong text return 403. Ten offline tests in tests/runtime/test_n8n_dynamic_webhook_contract.py and official cross-surface gate. No GPT live, Cloudflare auth or Chromium-over-n8n yet. Details in docs/architecture/p4-n8n-dynamic-writer-isolated-20261019.md.

### Verified scoped native Codex filesystem/network profiles (19 Oct 2026)

Every model call in scripts/odyssey_agent_cycle.py now requires a real sandbox preflight using scripts/odyssey_codex_permissions.py. The reviewer profile prevents writes; the builder profile writes only to its temporary worktree. Both deny host root by default, disallow private home/DEV/data reads and direct sockets, permit minimal system tools, approved Git repository objects, AGENTS.md and the worktree. Any failed preflight prevents launching Codex; no fallback to built-in read-only (which was verified to READ private host paths). A real Codex Luna low smoke passed (9.1s, 10032 tokens reported), with three new kernel/profiles tests in cross-surface gate and a supervisor fail-closed test. See docs/architecture/agent-codex-native-permissions-20261019.md. This protects model-directed shell commands, NOT every possible future MCP tool or the trusted authenticated launcher. No auto-deploy.

### First genuine scoped autonomous multi-agent cycle (19 Oct 2026)

Job `agent-native-scope-autonomy-20261019`: a single scoped test-only feature was implemented automatically by Luna Builder, passed host Python/JS/Ruff gates, was approved by Generality, failed Quality when the reviewer treated an **optional** timeout regression as mandatory, then autonomously entered round 2 Builder which fixed the optional case and passed all gates. **NOT accepted**: 153831 total reported tokens (47400+34377+37376+34678) left 66169 below mandatory 100k reviewer reserve, correctly returning `blocked_insufficient_review_budget`; agent code stays in its branch with no merge. The supervisor has since been improved to check Builder+full-review reserve BEFORE any follow-up repair; at the round-1 balance it would have blocked before spending the 34678-token repair. Common reviewer instructions now disallow blocking missing explicitly optional criteria and tell auditors to trust the authoritative host gate rather than pytest availability in their restricted sandbox. Detailed evidence and restrictions: docs/architecture/agent-autonomous-scoped-pilot-20261019.md. This is a fail-safe autonomous run, **not** proof of a complete approved agent cycle.

### Cross-job local daily pacing — NOT official ChatGPT quota (19 Oct 2026)

The official `run --live` CLI now requires an explicit operator-configured weekly **Codex-CLI-reported token proxy**. Read-only: `python3 scripts/odyssey_agent_cycle.py pace`. Example configuration (only after the operator decides a real proxy): `python3 scripts/odyssey_agent_cycle.py pace --weekly-reported-proxy 700000 --reserve-percent 20` computes 80k reported tokens per Paris local day. This does NOT represent the account's actual 5-hour/weekly quota; check OpenAI Settings → Usage separately, including activity from Work/Codex Cloud. All jobs share one daily budget and historical session spend is attributed conservatively; the live launcher refuses to start without pacing. No exact intrasesion cap, no automatic next-day resumption or notification; multi-day self-resuming work remains a blocker. See docs/architecture/agent-daily-pacing-20261019.md.

### Manual resume of a daily-paused reviewer (19 October 2026, branch only)

Only if `status --job JOB` shows `phase=paused_daily_budget` and a `resume_checkpoint`, inspect `pace` and the budget quote first. After a fresh local day with operator-configured reported-token headroom, a deliberate `python3 scripts/odyssey_agent_cycle.py resume --job JOB --live` may continue the unfinished reviewer set. The validator will refuse any changed worktree/reviewer artifact/required role or failed gate, and previously completed sessions are not re-billed. A job blocked by its **total job budget**, or an interrupted Builder, is NOT resumable by this command. There is **no scheduled auto-resume**, push, deploy, account quota integration, or notification. See [checkpoint evidence](../../docs/architecture/agent-review-daily-checkpoint-20261019.md).

### Builder-stage local daily pause (branch only, 19 October)

A staged Builder may now enter `paused_daily_budget` when the **pre-launch** daily pacing guard refuses it, including on later repair rounds. Inspect `status --job JOB`, `pace`, and `route --job JOB` read-only. Only the operator may invoke `resume --job JOB --live` when both daily reported-token headroom and the original total per-job review reserve are available. Resume checks the same worktree bytes, brief, declared role policy and previous repair evidence, then reruns normal product gates; it will NEVER replay an already completed model or restore partial in-flight execution. No automatic resume or billing/quota guarantee is implied.

### Scoped blocked final Quality review — explicit one-shot recovery (19 October 2026)

For a **tooling-only** job that completed all host gates and whose LAST mandatory reviewer returned only `BLOCKED` on unavailable external evidence (all earlier required reviewers PASS), `python3 scripts/odyssey_agent_cycle.py retry-blocked-review --job JOB --live` attempts exactly ONE strictly reviewed continuation; it does **not** re-run Builder or earlier reviewers. It is NOT available for product features, failed reviewers, a partial Builder, changed source or an unproven historical snapshot. The operator must explicitly invoke it, and a real configured day quota with 40k headroom plus remaining per-job reserve is required.

The method checks the isolated worktree/allowlist, original read-only reviewer artifacts, original gate and source fingerprint, then reruns the full authoritative host gates and a fresh single read-only specialist. The original BLOCKED artifact remains preserved in `review_recovery_history` and the recovery receives a distinct artifact path. Only a new PASS plus green gates can yield tooling maintainer readiness. No automatic scheduling or deploy/merge authority results. For historical jobs missing the source hash, a manually established matching and PASS independent Quality diagnostic is mandatory: do not pretend an old unsourced verdict is trustworthy.
