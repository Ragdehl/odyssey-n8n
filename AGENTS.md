# Odyssey agent instructions

## Goal

Odyssey turns unstructured personal information into durable, reusable knowledge. Canonical personal knowledge remains human-readable Markdown; automation should make capture and retrieval easier without replacing the user's files with a second authority.

A single request may retrieve knowledge, create or update several notes, resolve references, or combine reads and writes. Preserve stable identity and fail closed when identity or mutation authority is ambiguous.

## Current architecture

```text
external client
     |
     v
n8n integration/orchestration
     |
     v
thin Odyssey runtime
     |
     v
odyssey_core/
     |
     +--> canonical Markdown in /data/odyssey/vault
     +--> durable non-knowledge state in /data/odyssey/state
     `--> rebuildable runtime/index state in /data/odyssey/runtime
```

The current standalone consumer source lives under `odyssey_web/` as part of Phase 20. ChatGPT or other clients may also consume Odyssey, but no client owns the knowledge semantics.

- `odyssey_core/` owns domain, note, identity, planning, retrieval, validation, and mutation behavior.
- `workflows/` owns n8n integration/orchestration definitions.
- Markdown is authoritative personal knowledge.
- SQLite/indexes/embeddings/caches are derived and rebuildable.
- `config/note-schema.json` is the machine-readable canonical schema.
- n8n, browser code, and model providers must not become alternate semantic authorities.

Do not introduce LangGraph, a vector service, graph database, queue, additional application server, or other infrastructure unless a concrete requirement cannot be handled cleanly by the current boundaries.

## Development principles

- Prefer the simplest working solution and challenge unnecessary complexity.
- Understand the user-visible requirement before optimizing implementation details.
- Keep changes small, reviewable, and testable; avoid unrelated edits.
- Put Odyssey knowledge/domain logic in `odyssey_core/` by default and integration/orchestration in `workflows/`.
- Prefer native n8n behavior when it solves an integration problem cleanly; use custom code when it gives a clear contract or safety advantage.
- Reusable workflows/subworkflows should expose narrow, explicit input/output contracts and hide implementation details from callers.
- When architecture, workflow, or component interactions are easier to understand visually, use a concise text/ASCII diagram; omit decorative or redundant diagrams.
- Keep components replaceable behind explicit contracts.
- Never silently change the ontology/schema. Material schema changes require an explicit proposal, compatibility/migration review, deterministic validation, and normally human approval.
- Never expose, print, commit, or persist credentials/secrets in project files or documentation.
- Explain material architecture/security/data trade-offs before changing those boundaries.
- Do not delete or overwrite real personal knowledge as part of development evidence.

Production Python is for human readers. Functions and methods must have useful functional docstrings describing domain responsibility, parameters, returns when relevant, and meaningful errors. Add concise comments/examples only where behavior or safety reasoning is not obvious; do not narrate syntax.

Ruff is the Python lint/format authority and pytest is the Python test runner. Preserve existing unittest tests unless functional work already makes migration useful.

## Model-facing changes

Prompt evolution is inheritance-first. When introducing a model-specific, cheaper-model, experimental, or revised prompt for an existing capability/contract, start from the strongest existing validated prompt for that same behavior. Preserve established safety, semantic, and edge-case instructions by default; improve or adapt them rather than silently recreating the prompt from scratch. Any deliberate omission or simplification must be explicitly diffed, justified, and covered by regression sentinels before live evaluation. Model-specific wording may be shortened or reorganized, but previously validated behavior must not be dropped accidentally.

A deterministic test cannot prove that a production model follows a changed prompt or structured-output instruction.

Whenever a production LLM prompt, model-facing instruction, or structured-output contract changes materially:

1. keep deterministic schema/fail-closed tests;
2. run focused live evidence with the same production model and reasoning configuration;
3. include a compact regression-sentinel set for prior behavior the change could disturb;
4. reuse frozen cases/oracles where possible rather than rerunning unrelated model selection;
5. if provider access is unavailable, report the missing live-evidence gate explicitly instead of treating the change as validated.

Before changing a prompt because a sentinel failed, determine whether the model regressed or the oracle is over-constrained.

## Development autonomy and confirmation

On a feature branch, proceed autonomously with routine, reversible, in-scope work: repository edits, tests, validators, isolated disposable fixtures, development/test n8n executions, review fixes, commits/pushes, and Draft PR creation/update.

Ask before actions with material data, security, architecture, or irreversibility risk, including:

- modifying/deleting real personal data in `/data/odyssey/vault`;
- destructive migrations, database/volume resets, or important live-workflow deletion;
- credential, OAuth-scope, permission, filesystem, network, Cloudflare, or other security-boundary changes;
- new services or material architecture outside the approved scope;
- force pushes/destructive Git history rewrites;
- direct pushes to `main`;
- merging a Pull Request;
- material product/contract ambiguity that cannot be inferred safely.

Routine implementation risk means proceed; material authority/security/data risk means ask. A failed final verification means the branch is not ready, not that coherent work should be discarded.

## Significant functional phases

For a significant functional phase:

1. read the canonical [Functional Roadmap](docs/architecture/functional-roadmap.md);
2. read the relevant current architecture contracts and ADRs;
3. define objective, acceptance criteria, out-of-scope work, and open decisions under the [Development Pipeline](docs/architecture/development-pipeline.md);
4. run the repository `odyssey-architecture-challenge` skill before implementation;
5. implement code and tests together;
6. run focused checks during iteration and `odyssey-verify-change` before declaring readiness;
7. create/maintain a Draft PR until deterministic CI and semantic review are clean;
8. human merge only;
9. after merge, use `odyssey-post-merge` for safe synchronization/branch cleanup when the local environment is available.

When discussion creates a real future requirement or functional direction, preserve it in the roadmap or the appropriate canonical future-direction document. Do not leave project direction only in chat, an issue, a PR description, or agent memory.

## Operational learning and incident closure

When a non-trivial bug, deployment drift, hidden precondition, environment mismatch, or operational failure is diagnosed, the task is not complete when the immediate symptom disappears. Preserve the reusable learning before closing the work.

- Record the learning in the smallest canonical owner: phase/benchmark docs for checkpoint evidence, infrastructure/runbook docs for operational recovery, architecture/storage docs for durable invariants, and future-direction docs for deferred product work.
- Capture only what will help the next occurrence: **symptom or trigger, affected boundary, root cause, corrective action, verification evidence, and the preventive diagnostic/check**. Add rollback/safety constraints when the fix touches live data, security, credentials, networking, or deployment state.
- Prefer converting a discovered failure mode into an executable guard when practical: deterministic test, preflight assertion, deployment fingerprint/drift check, health probe, validation command, or runbook checklist. If automation is not justified yet, document the manual check explicitly.
- Distinguish **observed live state** from intended/configured state. Never document a live fix, migration, activation, or cleanup as complete until its post-change verification has actually passed.
- Do not turn `AGENTS.md` into an incident log. This section defines the capture discipline; actual incidents and solutions belong in their canonical technical owner and should be linked instead of duplicated.
- If a debugging path required multiple layers to isolate the fault, preserve the shortest reusable boundary-isolation method so future agents do not repeat broad trial-and-error.

The [Development Pipeline](docs/architecture/development-pipeline.md) owns the detailed close-the-loop process. Git/PR history alone is not a substitute for a still-needed operational invariant or recovery procedure.

## Implementation routing

Use the smallest executor that can validate the work reliably:

- a GitHub-capable agent is appropriate for bounded documentation/status changes, PR review, and small well-understood code changes whose validation can rely on deterministic CI;
- use Codex when local repository execution, iterative debugging/testing, broad multi-file implementation, benchmark work, Raspberry/Docker/filesystem access, or environment interaction materially improves reliability.

The author never gains merge authority. Deterministic CI, semantic review, and human merge remain separate gates.

## User-facing agent prompts

When preparing a prompt for Codex or another development agent for the user:

- write the reusable prompt in English unless the user explicitly asks for another language;
- always accompany it with a concise Spanish summary explaining the objective, what the agent is expected to do, and the important safety/cost constraints;
- include the recommended model and reasoning effort, with a short cost/capability rationale when model choice is relevant;
- do not omit the summary just because the prompt itself is long.

### ChatGPT-to-agent handoff communication preference

This is an assistant-facing communication preference for the ChatGPT project assistant,
not an execution instruction for Codex or another implementation agent. Before ChatGPT
gives the user a Codex prompt, it should briefly explain in Spanish what is happening
functionally and technically, why the Codex step is needed, which component or boundary
is involved, what Codex will touch and deliberately leave untouched, and what result is
expected. After the user returns Codex output, ChatGPT should first explain in Spanish
what Codex found or changed, what that means functionally, what happened technically,
whether it matches the expected architecture and safety contract, and what is unblocked
or remains pending. Keep the explanation concise but informative; use a small ASCII
diagram when it materially clarifies the handoff.

## Documentation ownership

Odyssey deliberately keeps few **canonical owners** and links to them instead of copying their content.

```text
README / product vision        -> product entry point and durable promise
overview                       -> current architecture
functional-roadmap             -> current phase/status and intended order
knowledge-model-direction      -> current knowledge representation
note-schema + JSON             -> schema interpretation + exact machine schema
storage                        -> data authority/storage ownership
future-* / platform directions -> intentionally deferred contracts
phase docs / ADRs / benchmarks -> historical contract/evidence
```

Rules:

- Current status belongs in `functional-roadmap.md`, not repeated across historical phase documents.
- Current system shape belongs in `overview.md`; phase documents may preserve checkpoint-local wording for historical evidence.
- Exact schema fields/types live in `config/note-schema.json`; prose explains principles and boundaries rather than copying the registry.
- One future capability should have one detailed owner. `future-extension-points.md` is primarily an index plus cross-cutting directions that do not have their own document.
- Do not create a separate Markdown document for every function, workflow, benchmark, or subphase when source code, tests, an ADR, or an existing canonical document already owns the durable contract.
- When a document becomes historical, keep it only if it preserves evidence/decisions not captured elsewhere; otherwise consolidate safely and update links.
- Documentation cleanup must not erase why a safety or architecture decision was made. Git/PR history is not a substitute for a still-needed durable contract, but it is sufficient for routine transient implementation detail.

## GitHub review workflow

Default to **one active PR at a time**. Do not open Draft PRs merely to remember future ideas or deferred product directions; preserve those in the canonical roadmap or appropriate future-direction owner instead. Multiple open PRs are appropriate only when a real dependency, review, or sequencing reason makes parallel/stacked work useful, and that dependency must be explicit. Before opening another PR, inspect the existing open PR set and merge, close, or consolidate obsolete/documentation-only work so deferred decisions do not become forgotten backlog.

Before continuing implementation on a branch with an open PR, use `odyssey-pr-feedback` to inspect review feedback. If comments conflict with each other or with an approved material contract, ask rather than guessing.

Use `odyssey-verify-change` before declaring a PR complete/ready. Verification is required for readiness; a safe checkpoint commit may still record an incomplete or blocked state explicitly.

Never delete an unmerged branch or a branch whose merge relationship is uncertain. Human approval is required for merge/deployment/security/destructive/credential/network/real-vault changes.
