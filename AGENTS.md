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

## Local-first ownership boundary

Odyssey's target product is local-first. One user's Odyssey instance owns that user's local vault and durable local state. In hosted or server-backed deployments, authenticated identity should select the isolated user-local vault/state root; once that root is selected, inner local repositories should normally be root-bound rather than redundantly modeling multiple users in their physical storage layout.

Future local/mobile clients should be able to reuse the same local storage semantics without requiring server-style multi-user partitioning. Multi-user identity, permissions, groups, and synchronization belong to the separate collaboration boundary used when knowledge crosses a sharing boundary. Private local-only knowledge or state must not become centrally hosted merely because collaboration exists.

Current DEV/server actor isolation must remain enforced at the outer authentication/root-selection boundary; local-first storage is not permission to weaken current isolation. See [Odyssey Platform Direction](docs/architecture/odyssey-platform-direction.md) and [Multi-user Collaboration Direction](docs/architecture/multi-user-collaboration-direction.md) for the durable product direction.

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

## Product ambiguity and inference

Do not turn an unstated assumption into settled product behavior. When a user-facing behavior,
retention rule, navigation model, domain semantic, lifecycle, or phase boundary has more than one
plausible interpretation and the canonical documentation does not already decide it, stop and ask the
human before implementing or documenting one interpretation as the product contract.

Do not treat nearby features, historical behavior, analogy with another product, implementation
convenience, or a likely user preference as authorization. During phase definition, surface uncertain
choices explicitly as **open decisions** and resolve them with the human before opening an
implementation PR when the user has asked to define the phase first. Routine mechanical choices
inside an already approved contract remain autonomous.

The fail-closed principle applies to product definition as well as mutation safety: when the product
contract is genuinely unknown, preserve the uncertainty rather than filling the gap with a guess.

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
- Before a live network/security mutation, inspect the complete current scope and the installed CLI/API semantics. Do not substitute broad commands such as `off`, `reset`, bulk replace, or recreate for an authorized narrow diff unless the live scope has already been proven to contain only that target and the authorization explicitly covers the broader effect.
- If read-only evidence or a mutation preflight contradicts an earlier diagnosis, stop and reconcile the live representation before mutating. If an approval system and execution transcript disagree about whether a command ran, treat the live state as `UNKNOWN` and perform read-only post-state verification before any further change.
- Do not treat a forwarded header name as proof of provenance. When identity or authorization depends on a proxy-added header, enumerate every ingress that can reach the same consumer and prove the relevant traffic crosses the trusted validation boundary or validate the assertion again at the consumer.
- Prefer authoritative provider documentation plus effective configuration evidence over inspecting real user tokens or identity payloads when those sources are sufficient to establish a security contract.
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

### Codex model-selection guidance

Recommend the **cheapest model and reasoning level that still has comfortable capability margin for the task's risk and complexity**. Do not default habitually either to the cheapest model or to the strongest model. State the recommendation explicitly in each ChatGPT-to-Codex handoff and give a short reason so the human can judge the cost/capability trade-off.

Use task risk, ambiguity, cross-boundary reasoning, and likely change amplification as the main signals. The current practical heuristic is:

- small mechanical edits, bounded documentation/tests, or already-diagnosed fixes -> prefer the cheapest capable tier, typically Luna Low/Medium when available;
- ordinary implementation with a settled contract and moderate multi-file reasoning -> prefer the middle capability tier, typically Terra Medium/High when available;
- architecture challenges, ambiguous cross-boundary debugging, security/networking/production incidents, or decisions where a wrong conclusion can amplify into substantial rework -> prefer Sol High;
- escalate beyond that only when evidence shows the lower recommendation is insufficient.

These model names are examples of the current lineup, not a permanent task-to-model binding. Re-evaluate as model capabilities, pricing, and availability change while preserving the cost/risk principle. Do not downgrade a high-risk task solely to save tokens when error amplification is likely, and do not spend Sol-class capacity on routine work merely by habit.

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
