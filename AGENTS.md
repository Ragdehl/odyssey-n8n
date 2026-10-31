# Odyssey — always-on agent contract

**Read this before modifying Odyssey.** This is the small set of rules that must not depend on skill discovery. The active project status is `docs/architecture/functional-roadmap.md`; older phase reports are **historical evidence**, never live deployment authority. For any new task/resume, use `odyssey-start-work` and `python3 scripts/odyssey_context_doctor.py`.

## Product, authority and architecture

**Target: installable, local-first mobile app.** Each device/profile keeps its own canonical Markdown vault and local durable state; basic notes and local operations must not depend on n8n, Cloudflare, a remote account or optional future sync. Today's Raspberry/browser service is an interim implementation, NOT proof that the mobile app is packaged or offline-ready. Sync is explicitly opt-in and must not replace device-local ownership.

Odyssey turns unstructured personal information into reusable, local-first Markdown knowledge. The user's canonical knowledge is Markdown, not n8n responses, browser state, model output, vector indexes or SQLite caches. `odyssey_core/` owns generic domain, identity, planning, validation and canonical persistence. `odyssey_apps/` owns only app-specific interpretation/lifecycle. `odyssey_runtime/` composes trusted boundaries. `workflows/` orchestrates n8n. `odyssey_web/` presents and sends user interactions. Do not import Apps into Core or create a competing writer/authority.

**Core/E3 is the only canonical mutation authority.** Router routes exact-original-source groups; Temporal supplies bounded date evidence; Apps supply their own specific semantics; **none** independently authorizes identities, links, plans or writes. Keep exact source/provenance, authenticated actor/context isolation, checked readback, concurrency, idempotence and negative/ambiguous refusal. Avoid LangGraph, extra databases/services, blanket rewrites and new infra without a concrete approved requirement. Incremental Clean Architecture: reuse the existing shared contracts and extract ports only when real coupling warrants it.

**Acceptance tests are input → final effect.** The 27 original + appended scenarios must run with fresh provider calls and genuine user browser actions at each final stage, then compare source meaning to physical Markdown/Task/Event/Notes/Calendar/reload/replay. Router/Temporal/Planner traces diagnose discrepancies but are not the expected output format; equivalent, safe representations are allowed when they account for every supported fact/action, avoid invention and have independent evidence. The acceptance stage cannot be closed by recorded responses, a chat ACK or partial intermediates.

**Generality is mandatory.** A Router candidate may map to zero, one or many Core facts; multiple candidates may produce a fact. No fixed candidate/participant counts or branching on example strings, names, pronouns, punctuation, language or corpus IDs. Always fix shared mechanisms and test all consumers, never just the example. For semantic, Router, Core or App work use `odyssey-generality`, `docs/architecture/application-extensibility-plan.md` and the currently approved hybrid contract.

**Human-approved singular identity rule:** a singular typed identity without a safe existing match may be created by Core only if there is genuinely no conflict; do not silently turn it into a literal. Complete-set/group language may remain literal when canonical members cannot be grounded. Ambiguous, stale or contradictory evidence must fail closed. A proposal changing this product contract needs human approval first. Never silently change NoteSchema/ontology without explicit contract, migration and validation review.

## Safety and autonomy

On a clean isolated worktree, proceed autonomously with reversible, in-scope edits, focused tests, synthetic fixtures, read-only review and checkpoint commits. Do not overwrite unexpected/uncommitted files or race another agent/deployment. **Ask before** irreversible/destructive changes, real personal data in `/data/odyssey/vault`, PROD, permission/network/credentials changes, major architecture or schema, force pushes, direct `main` pushes or merging PRs. Neither a feature branch nor a passing suite authorizes a deploy or a merge.

**No secrets in code, notes, CLI output or logs.** A Remote Desktop shell normally lacks `OPENAI_API_KEY`; this is expected. The existing protected OpenAI EnvironmentFile is `/home/ragdehl/.config/odyssey/secrets.env`; use the bounded transient `systemd --user` method in `odyssey-live-provider`. Check presence/configuration without revealing the secret. Never infer an outage from a missing shell variable or ask again for a key already configured. Billable real-model tests require bounded authorization.

## Model-facing work

When changing any Odyssey LLM prompt, provider schema, model/effort or reviewer, **invoke `odyssey-llm-stage`**. Inherit the strongest existing accepted prompt/schema for that behavior instead of starting blank; preserve safety/examples unless deliberately diffed, justified and regression-tested. Strict typed output, bounded source/context, abstention and independent completeness review must survive. Frozen genuine provider replay ≠ newly tested production-model behavior. Do not update accepted prompt hashes just to turn CI green; run an explicitly authorized, scoped real-model gate before claiming model-facing readiness.

Developer Codex model/effort selection is separate from the actual Odyssey runtime model. Choose the cheapest **sufficiently capable** developer model for task complexity; use stronger reasoning for security/architecture. Never downgrade high-risk work solely to save tokens.

## Workflow, evidence and documentation

1. **Start/resume:** read top of `docs/architecture/functional-roadmap.md`, relevant normative contracts and this file; run `odyssey-start-work` / read-only context doctor, check source SHA, DEV checkout/marker, PRs and concurrent agents. Do not confuse branch, GitHub merge and deployed version.
2. **Significant phase:** define objective, acceptance, out-of-scope and open decisions, then use `odyssey-architecture-challenge`. Stop for genuinely material unresolved product behavior, not routine mechanical details.
3. **Implement generally:** explicitly read `odyssey-implement-change` for code changes; keep minimal coherent diff, useful Python docstrings, typed contracts, no unrelated changes or permanent per-example exceptions. Ruff and pytest are authoritative for Python.
4. **Verify:** focused unit/contract **and vertical E2E regressions** for functional changes; before readiness use `odyssey-verify-change` and the full `scripts/odyssey_cross_surface_gate.py`. Model-facing changes need the live gate above. DEV adoption needs actual browser→n8n→GPT→Core/E3→Markdown→browser proof, synthetic data and matching deployed SHA. See `odyssey-dev-e2e`.
5. **Review/PR:** default to **one active PR**, inspect existing PR feedback with `odyssey-pr-feedback`; keep CI/independent review separate from author. Human merges. `odyssey-post-merge` operates on the PR's **actual base branch**; never automatically assume `main`.
6. **Close and progress updates:** explicitly read `odyssey-results` before **every Odyssey development progress response**, even if no code changed; show one concrete **done/observed before→after** example and one **next/expected input→result→test** example. Never describe an existing mechanism as a fresh phase without looking for its prior implementation. Use `odyssey-results` for a consistent user-facing summary with evidence/4-role audit status, what remains in this phase and roadmap ahead. Record commit/PR, exact deployment state, limitations and next step in **one** canonical status owner. Capture user-requested future capabilities in the [near-term backlog](docs/architecture/near-term-product-backlog-20261025.md) with priority, clear examples and non-goals; do not treat an idea as an implemented feature or deployment permission. Record a reusable operational failure as symptom→cause→fix→verification→prevention in the appropriate runbook, not here. Do not claim completion or re-run all auditors when evidence is missing or stale; classify the blocker and close the narrow gap.

## Skill directory and canonical references

- `odyssey-start-work`: every task/continuation, Git/worktrees/deployment state.
- `odyssey-implement-change`: every coding/change task; find the right owner, reuse existing code, write negative/vertical tests and load scope-specific skills.
- `odyssey-diagnose-first`: every reported bug, missing expected behavior or early refusal; trace existing owners, active flags and real failure before proposing implementation.
- `odyssey-generality`: Router/Temporal/Core/Apps, future extensibility.
- `odyssey-llm-stage`: creating/editing prompts, models, validators/reviewers.
- `odyssey-live-provider`: OpenAI EnvironmentFile, authorized real-model cost.
- `odyssey-dev-e2e`: DEV deployment, browser regressions and safe recovery.
- `odyssey-results`: report verified progress consistently, including examples, test/audit state, immediate and later roadmap, and exact Git/DEV status.
- `odyssey-skill-steward`: notice repeated workflow mistakes or reusable corrections and improve existing skills before proposing a new one. Use the installed official Codex `skill-creator` for skill design and validation; do not add skills for isolated bugs.
- `odyssey-ux`: modern UI design and review against Anthropic `frontend-design` and Vercel `web-design-guidelines`, then actual Chromium mobile/desktop acceptance.
- Existing: `odyssey-architecture-challenge`, `odyssey-verify-change`, `odyssey-pr-feedback`, `odyssey-post-merge`.

Skills are stored in `.codex/skills/<name>/SKILL.md`. A ChatGPT/Remote Desktop worker may **not auto-load** them: explicitly read the relevant skill. Detailed ownership: `docs/architecture/instruction-map.md`; current architecture `docs/architecture/overview.md`; schema `config/note-schema.json`; full process `docs/architecture/development-pipeline.md`; deployment/secret runbook `docs/infrastructure/raspberry-runtime.md`. Historical model and phase claims are not standing permission.
