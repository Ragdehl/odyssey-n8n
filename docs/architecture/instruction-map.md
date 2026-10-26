# Odyssey instruction map — one current owner per decision

Use [AGENTS.md](../../AGENTS.md) as the **small, always-on safety contract** and [Functional Roadmap](functional-roadmap.md) as the **only live implementation state** (verify against Git/DEV). The complete [historical roadmap](functional-roadmap-history-20261023.md) remains immutable evidence, not current status. The system must not assume that simply adding a Codex skill auto-loads it in a ChatGPT Remote Desktop session.

## Skill selection and triggers

| Trigger | Skill | Normative detail owner |
| --- | --- | --- |
| Start/resume development, investigate apparent lost context, check concurrency | [odyssey-start-work](../../.codex/skills/odyssey-start-work/SKILL.md) | Current roadmap, `scripts/odyssey_context_doctor.py`, Git/runtime |
| New semantic logic, App, identity or N:M candidates | [odyssey-generality](../../.codex/skills/odyssey-generality/SKILL.md) | Hybrid [Router contract](router-hybrid-interpretation-contract.md), [App plan](application-extensibility-plan.md), E2/E3 |
| Create/change LLM role, prompt, provider JSON schema, reviewer/model/effort | [odyssey-llm-stage](../../.codex/skills/odyssey-llm-stage/SKILL.md) | Current prompt/parser/schema in code + tests, protected accepted hashes |
| Access authorized real OpenAI/provider experiment or missing shell key | [odyssey-live-provider](../../.codex/skills/odyssey-live-provider/SKILL.md) | [Raspberry operational runbook](../infrastructure/raspberry-runtime.md) |
| Real DEV launch, UI testing, recover n8n/deploy, browser regressions | [odyssey-dev-e2e](../../.codex/skills/odyssey-dev-e2e/SKILL.md) | [DEV isolation](phase-21-development-isolation.md), [Testing](testing.md) |
| Challenge a significant new project phase | [odyssey-architecture-challenge](../../.codex/skills/odyssey-architecture-challenge/SKILL.md) | [Development pipeline](development-pipeline.md) |
| Check readiness of code / tests / release | [odyssey-verify-change](../../.codex/skills/odyssey-verify-change/SKILL.md) | [Testing](testing.md), `scripts/odyssey_cross_surface_gate.py` |
| Results/progress, what was done, examples, what remains and later phases | [odyssey-results](../../.codex/skills/odyssey-results/SKILL.md) | Current roadmap, actual SHA, PR, CI, DEV and audit receipts |
| Existing PR comments, existing branch | [odyssey-pr-feedback](../../.codex/skills/odyssey-pr-feedback/SKILL.md) | GitHub's **actual PR**, not a guessed one |
| Repeated agent error, repeated instruction or skill improvement candidate | [odyssey-skill-steward](../../.codex/skills/odyssey-skill-steward/SKILL.md) | First-party Codex skill-creator, reuse existing skill before adding a new one |
| Confirmed PR merge then synchronize and prune only its branch | [odyssey-post-merge](../../.codex/skills/odyssey-post-merge/SKILL.md) | Actual PR base branch (often `dev`), never always `main` |

New LLM work should normally load **start-work + llm-stage**, and **generality** if Router/Core/app contracts change; **live-provider** only if a billable real provider gate is authorized; **dev-e2e** only if deployment/browser validation is in scope. Do not eagerly dump all skills into every prompt.

## Durable contracts vs history

- **Schema and knowledge authority:** `config/note-schema.json`, [overview](overview.md), [storage](storage.md), `odyssey_core/`.
- **Hybrid/Source/Context/E3 boundaries:** [Router contract](router-hybrid-interpretation-contract.md), [E2 context](e2-shared-context-contract.md), [App extensibility](application-extensibility-plan.md), code and acceptance tests.
- **Current state and next milestone:** [Functional Roadmap](functional-roadmap.md) only. Do not append a series of dated 'CURRENT' paragraphs.
- **Raspberry/DEV/provider execution:** [Raspberry runtime](../infrastructure/raspberry-runtime.md), [DEV isolation](phase-21-development-isolation.md), live operator + measured state.
- **Historic results, experiment budgets and superseded guidance:** dated reports in `docs/architecture/`, [archived roadmap](functional-roadmap-history-20261023.md), `benchmarks/` and `docs/decisions/`. These are not live permission.
- **Agent supervisor policy:** `ops/agent-team/README.md` and its scripts/policy; do not mistake an old pilot's model, budget or audit status for today's deployed configuration.

## Conflict resolution

1. The user's newest explicit decision and binding safety rules prevail; model memory is not current Git/DEV evidence.
2. Read the **code + active deployed SHA**, then current roadmap, normative contract/ADR, and only afterward relevant dated reports. A historic claim "not deployed" remains true about its own checkpoint but **cannot describe today's DEV**.
3. When two operational runbooks contradict each other, **stop and reconcile once**, update the single owner and link to it instead of copying both procedures into AGENTS.
4. An environment or missing key may be expected; check the correct protected systemd EnvironmentFile and manager without exposing values.
5. When a rule should never be forgotten (generalization, Core/E3 authority, human approvals, provider security), keep a concise always-on version in AGENTS and put the detailed procedure here or in the appropriate skill.
6. No live-provider/deploy/merge is authorized by documentation cleanup alone.

Use `python3 scripts/odyssey_context_doctor.py` to inspect read-only local reality and `python3 scripts/odyssey_docs_guard.py` to validate file links and skills. These tools deliberately never read or print credential values.
