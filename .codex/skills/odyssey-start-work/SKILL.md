---
name: odyssey-start-work
description: Start or resume Odyssey work; reconcile source, worktrees, concurrent agents, deployed DEV, Git/PR state and canonical next step. Use before implementation, debugging, audit, continuation, or deployment.
---

# Odyssey start-of-work and continuity

1. Read **AGENTS.md** and the top `Current state` section of `docs/architecture/functional-roadmap.md`; read only relevant contracts. Historic phase reports are evidence, not live authority.
2. Run `python3 scripts/odyssey_context_doctor.py` (read-only, never dumps credentials). Check `git status -sb`, SHA/upstream, active worktrees, PRs, processes and DEV Git/marker/health separately.
3. If concurrent work or dirty files exist, **do not reset, stage or overwrite them**. Work in a clean isolated checkout pinned to a SHA, or pause the conflicting operation. A deployment must never chase moving HEAD.
4. Choose smallest change and tests. Identify product-contract ambiguity, E2/E3/Core owner, approval needed, disposable data, backup and rollback.
5. At completion report exact **tested** commit and evidence; distinguish source, GitHub merge, deployed runtime marker and browser E2E. Update a single canonical status owner, not a new timestamped 'CURRENT' paragraph.

Avoid terminal polling loops: check the relevant process and log, diagnose the boundary once, and fail closed on unknown deployment state. See `docs/architecture/development-pipeline.md` and `odyssey-dev-e2e`. This skill does not grant deploy, merge, credential, provider-spend or production authority.
