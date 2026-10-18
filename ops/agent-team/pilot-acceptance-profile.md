# Pilot feature — product vs tooling acceptance profiles (real model-budget experiment)

## Scope and user goal
The supervisor currently returns `reviewed_browser_gate_pending` for **every** successful review, even an internal CLI-only tool change that cannot possibly be exercised through Odyssey's UI. Add a small, declarative acceptance-scope mechanism **only to the development supervisor**, not to Odyssey Core, Tasks, Calendar or any application.

This is an A/B-style observational pilot of the new economical agent configuration: preserve actual model attribution, CLI-reported token count, wall-clock timing, gate evidence, and output quality for every participant. All agents should read project governance and this brief. No manual coding by ChatGPT within the agent cycle.

## Acceptance criteria
1. `plan` accepts `--acceptance product|tooling`, default `product`. Save a validated acceptance profile in the job's status JSON.
2. When the automated gate and all independent reviewer verdicts are PASS, **product** continues to return `reviewed_browser_gate_pending` with `ready_for_user=false` until genuine browser→n8n→Writer evidence.
3. For **tooling** only, a successful CLI-only review may reach a distinct unambiguous `reviewed_tooling_ready` state, with `ready_for_user=true` meaning "internal CLI feature ready for maintainer", NOT authorization to deploy Odyssey or merge/push code.
4. **Fail closed:** tooling scope must never be user-selectable for changes to any Odyssey product code, including `odyssey_core/`, `odyssey_runtime/`, `odyssey_apps/`, `odyssey_web/`, `workflows/`, `config/`, or the product acceptance ledger. Check the real working tree diff since the pinned Git baseline plus untracked modifications AFTER Builder; unknown/unsafe path should block even if all models approve it. Document this explicit allowlist or defensible equivalent: `scripts/odyssey_agent_cycle.py`, `tests/runtime/test_agent_cycle_supervisor.py`, `ops/agent-team/`, and agent-team docs only. A product code change on a tooling profile MUST remain blocked (without deploy). No broad loophole for user-created future apps.
5. Tests cover both authors (Codex or ChatGPT), default/product behavior, tooling success with four PASS, tooling with one failed/blocked reviewer, product path tampering fail-closed, persistence/replay of decision, and absence of shell side effects. Do not hardcode a literal job name, note type, action count, or example string into product code.
6. Run focused tests, Ruff; supervisor runs full cross-surface suite and acceptance ledger once per round outside Codex sandbox. Avoid re-reading historical documentation and running global tests from inside Codex.

## Safety and timing
Use exactly the isolated git worktree of this job. Never push, merge, deploy, alter DEV/PROD, open credentials, read personal vaults, change network routes, disable checks, or modify historic benchmark cost ceiling. Single Pi CLI Codex session at a time; bounded by configured reported-token budget. This feature affects only the agent supervisor, not the actual Odyssey application or user-created apps. The GUI browser gate is **not required for tooling** but remains mandatory for product.
