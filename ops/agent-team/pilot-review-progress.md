# Pilot feature — visible incremental review progress (CLI supervisor only)

## Problem
The supervisor currently updates `active_role` before each reviewer, but stores `state["reviews"]` only after ALL reviewers have completed. If the user checks `status` during a multi-minute audit, it conceals which reviewers have already passed/failed and their findings. If the supervisor terminates mid-review, completed reviews should remain visible for diagnosis.

## User-facing acceptance
Implement this generic, persistent behavior in `scripts/odyssey_agent_cycle.py` without changing Odyssey product routing/Task/Calendar/Writer:
1. After EACH successfully completed reviewer, immediately save that review verdict and relevant evidence/artifact in the JSON job status while continuing the SAME sequential review workflow.
2. If a reviewer fails, the already-completed reviews must remain available and the run must fail closed, without claiming approval.
3. Starting a NEW repair round must not accidentally present reviews from the PREVIOUS round as if they applied to the latest implementation; preserve former round's evidence in its own files, and expose which round is active in the JSON state.
4. Preserve ChatGPT-authored and Codex-authored first round distinctions, global one-process mutex, stop and time budgets, exit codes, no deploy/push/merge/PROD access.
5. Write focused deterministic tests showing live status after first and second reviewers, review failure preservation, and clearance when a new round starts. The code must have no conditional on literal role names or a fixed count of reviewers.
6. Run focused pytest, Ruff, cross-surface tests and acceptance ledger. A reviewer may run a safe CLI status benchmark, reporting p50/p95 from a repeatable count of >=30 calls on the real Pi when possible. A CLI-only supervisor change requires no authenticated browser→n8n→product deployment gate; state this explicitly rather than fabricating UI evidence.

## Boundaries
Work ONLY in a fresh isolated Git worktree and local synthetic job state. No real user notes, no PROD/DEV vault or deployment, no secrets, no GitHub push, no Cloudflare/n8n actions, no disabling security checks, no modifying benchmark pricing ceilings. The independent reviewers should audit the feature's diff, not block on unrelated pre-existing P4 app extensibility problems. Changes may include general supervisor tests and relevant docs; do not broadly rewrite the agents.
