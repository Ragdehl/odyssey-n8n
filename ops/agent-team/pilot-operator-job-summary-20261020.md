# Next real agent pilot — useful read-only job summary for the operator (20 Oct 2026)

## Goal
Demonstrate that the **already functioning Odyssey autonomous Codex Builder + independent reviewers** can build a small, useful, testable CLI feature from this brief. The operator should be able to inspect progress and completion without reading large internal JSON. The result is a maintainer utility, **NOT an Odyssey product/UI feature or DEV deployment**.

## Deliverable
Implement a small **read-only** command at `ops/agent-team/job_summary.py` that runs from the repo root using
`python3 ops/agent-team/job_summary.py --job agent-resume-quote-pilot-20261019`.
It must return a concise human-readable report (Spanish or English acceptable) showing ONLY:
- job identifier, phase, round, readiness for maintainer (true/false)
- selected mandatory auditor roles with their *real* per-role verdicts (e.g. Generality PASS, Quality PASS); never present omitted reviewers as PASS
- cumulative CLI-reported tokens used and assigned per-job total cap
- optional original BLOCKED plus new PASS on a recovered review, clearly distinguish the original result from the accepted retry.

Implement `--json` for a minimal stable machine-readable subset of the SAME safe fields, useful for future UI/status. Print an error and exit nonzero for an unknown/malformed job identifier or an unavailable/corrupt status. Do not log raw stored prompts, history text, credentials, environment variables, private paths, or the entire status JSON. Never infer the actual ChatGPT subscription quota or falsely claim a product deployment.

## Scope
- ONLY create `ops/agent-team/job_summary.py` and add focused regression tests to existing `tests/runtime/test_agent_cycle_supervisor.py`. No other paths may be changed by Builder, including policy, supervisor, AGENTS.md, product, workflows and docs. Use the supervisor's existing validated job loading and read-only state; avoid new stores, servers, processes, MCP connectors or dependencies. Never modify jobs or create STOP markers. No deploy, no merge, no push, no network calls, no real personal vault.
- Tests use a synthetic, tempfile-owned status with two independent role verdicts, one recovered BLOCKED review, no approval cases, and unknown job. Verify text and JSON variants and reject accidental exposure of extra source fields or paths. Import/run command without granting filesystem writes.
- Focused tests and Ruff in the Codex sandbox if available, otherwise state clearly when the sandbox does not provide pytest/Ruff. The deterministic host supervisor will run the full Python+JS/ledger/Ruff gates as the authoritative receipt.

## Independent acceptance and limits
This is **internal tooling, declared normal risk**, so the configured specialist policy requires separate Generality + Quality review (and all standard deterministic gates); Testing and Performance model reviewers are intentionally omitted under this scope, NOT automatically approved. If the change touches risk-sensitive supervisor/policy files, the risk escalates and normal review savings are not allowed.

Use the existing isolated worktree sandbox. No production or DEV writes, no real actors or personal data. Maximum two bounded rounds; consume only existing authorized Codex CLI subscription headroom and the configured daily/proxy and per-job reserves. A reviewer may FAIL/BLOCK; do not fabricate approval or silently lower gates. On successful review, the operator can run the new utility against the prior saved job and visually check the status. This test does **not** validate P4 browser→n8n→live GPT→Writer product E2E and never authorizes deployment.
