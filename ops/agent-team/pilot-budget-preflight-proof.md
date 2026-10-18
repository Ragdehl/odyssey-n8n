# Low-risk tooling evidence: deterministic risk + cost guard

This is a documentation-only deliverable for the Odyssey development supervisor. It is intentionally limited to `ops/agent-team/`; it does not change source code, user-owned notes, product Core, workflows, n8n or UI. Both generic architecture and code quality / security reviewers should independently verify that the evidence is consistent with the current repository's `scripts/odyssey_agent_cycle.py`, `ops/agent-team/model-policy.json`, the observed dry-run state, and the explicit restriction to internal tooling. They should not invent the verdicts of unselected roles; the supervisor performs final aggregation.

## Real verification to document

- A high-risk tooling job was planned against commit `e62aeb2` with a 110,000 CLI-reported-token budget and `--risk high`.
- The read-only `route` preview selected **all four** independent roles for high-risk work and quoted 205,000 minimum remaining tokens for these four roles. It did not launch models.
- `run --live --max-rounds 1` returned exit 3 **before creating an isolated worktree or launching any model**. Its recorded phase is `blocked_insufficient_review_budget`, `ready_for_user=false`, `token_usage.reported_total=0`, and the job has zero model session receipts.
- Actual original JSON proof: `/home/ragdehl/projects/.odyssey-agent-runs/risk-preflight-20261018/status.json`; `/tmp/odyssey-risk-preflight-route.json`. These are local and do not grant private data access.
- The 110,000 default reported-token ceiling is **not sufficient for product acceptance** or high-risk tooling; no budget may be silently raised.
- For a documentation-only `--acceptance tooling --risk normal` job, the policy still requires **generality and quality** plus all deterministic tests. QA/performance model sessions are explicitly omitted, **not considered passed**. If high risk is declared or any change is to an Odyssey product capability, all four specialists remain mandatory. Do not let a future user-created app disguise itself as tooling: file allowlist must block that.
- This document is not an authorization for deploying Odyssey DEV or PROD; product still requires an authenticated browser→n8n→Core Writer→readback gate.

## Acceptance

Independent Generality and Quality model audits of this single documentation-only change must both PASS with no blocking finding; the official Python+JavaScript cross-surface suite, ledger and Ruff must also PASS. Any missing evidence blocks rather than inventing test results. If the job is accepted, its terminal state must be `reviewed_tooling_ready` with two concrete model receipts and `ready_for_user=true` meaning internal tooling documentation ready for maintainer only. No push, merge or deployment and no permission escalation. Bound by the existing 110,000 reported-token budget and 40,000 next-session headroom.
