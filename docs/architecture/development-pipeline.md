# Development Pipeline

Odyssey evolves its development process only when the next step solves an observed problem. Git
history, pull requests, and test results remain the source of development state; this roadmap is
architectural direction, not a manually synchronized status tracker.

## Significant phase contract

Before implementation, a significant functional phase specification contains at least:

- **Objective:** the outcome and problem the phase addresses.
- **Acceptance criteria:** observable evidence that the phase is complete.
- **Out of scope:** nearby work intentionally excluded.
- **Open decisions:** unresolved choices, or `None` when there are none.

Context and constraints may be included when they materially affect the work. This is a
human/agent-readable convention, not a schema, parser, database, state machine, or orchestration
contract. Codex runs `odyssey-architecture-challenge` against the phase and relevant repository
context before implementation begins.

## Responsibility boundaries

```text
phase contract
    |
    v
architecture challenge (agent judgment)
    |
    v
choose the smallest reliable execution path
    |                         |
    |                         |
    v                         v
GitHub-capable agent       Codex local implementation
bounded change             + local iteration/debugging
    |                         |
    +------------+------------+
                 |
                 v
GitHub PR + deterministic server-side CI
                 |
                 v
semantic/human review and human merge
```

- GitHub owns branches, pull-request state, server-side checks, and any future merge protection or
  auto-merge policy.
- The GitHub-capable agent may implement bounded, well-understood changes directly when the contract
  is clear and reliable validation does not require an iterative local environment.
- Codex owns implementation that materially benefits from repository-local execution: iterative
  testing and debugging, broader multi-file changes, refactors, benchmark/harness work, environment
  interaction, and other tasks where local feedback is part of reaching a correct result.
- Choosing Codex is not automatic merely because code changes are required. Before delegation,
  prefer the smallest execution path that can complete the work safely and reviewably.
- Regardless of who writes the change, deterministic validation and semantic review remain separate
  gates. The author does not gain authority to merge its own work.
- Agents and LLMs provide judgment; they do not replace deterministic validation.
- Pre-commit provides fast local feedback when Codex is working locally, while GitHub CI
  independently validates commits and pull requests.
- n8n remains responsible for integrations, notifications, external orchestration, and eventual
  human-in-the-loop flows when a concrete need justifies them. It is not part of development CI.

### Implementation routing

Use this table as the default routing rule, not as a rigid prohibition. Escalate to Codex whenever a
nominally small change becomes difficult to validate safely through the GitHub path.

| Work | Default executor | Why |
| --- | --- | --- |
| Architecture/roadmap/ADR/status documentation | GitHub-capable agent | Direct reviewable edits; no local execution normally required. |
| Pull-request review, stale-doc review, architecture challenge | GitHub-capable agent | Requires cross-file judgment and independent review rather than repository-local iteration. |
| Small focused code change with an already-clear contract | GitHub-capable agent | Efficient when the change is bounded and CI can provide sufficient deterministic validation. |
| Simple data-model/schema-plumbing change with obvious tests | GitHub-capable agent when genuinely bounded | Keep it direct unless failures require iterative local debugging. |
| Multi-layer or broad multi-file implementation | Codex | Local repository exploration and repeated test feedback materially improve reliability. |
| Refactor or non-trivial debugging | Codex | Requires iterative execution, inspection, and correction. |
| Benchmark/harness implementation or repeated local experiments | Codex | Needs controlled local execution and evidence collection. |
| Raspberry Pi, filesystem, Docker, local n8n, or environment-sensitive work | Codex | Requires access to the actual local development/runtime environment. |
| Final semantic review of either implementation path | GitHub-capable agent + human as needed | Preserve independent review before human merge. |

The intended recurring workflow is therefore:

```text
need a change
    |
    v
Can the GitHub-capable agent implement it as a small, safe, reviewable change
without needing iterative local execution?
    |
    +-- yes --> implement on feature branch --> CI --> semantic review
    |
    `-- no  --> delegate to Codex --> local iteration --> PR/CI --> semantic review

Either path --> human merge
```

This routing decision is itself part of project process and should survive chat/session memory. If a
future agent is uncertain which route applies, prefer Codex when local feedback is necessary and the
GitHub-capable path when the work is genuinely bounded; do not create a second process document for
this distinction.

## Evolution points

- **D0 — manual stable workflow:** phase specification, bounded agent/Codex implementation as
  appropriate, verification, Draft PR, semantic review, and human merge.
- **D1 — Architecture Challenge + GitHub CI:** add a pre-implementation reasoning checkpoint and
  independent deterministic Python validation.
- **D1.1 — public readiness + verification efficiency:** remove unnecessary operational identifiers
  from public-facing content and avoid redundant local verification while preserving the complete
  deterministic gate.
- **D2 — independent Codex reviewer experiment:** evaluate only as a bounded later experiment.
- **D3 — semantic-review gate + GitHub auto-merge:** consider only after review evidence is reliable;
  GitHub continues to own merge policy.
- **D4 — automatic correction loop:** consider only if review and correction behavior proves safe.
- **D5 — automatic phase progression:** consider only after earlier gates are trustworthy.
- **D6 — `HUMAN_REQUIRED` + n8n/Telegram:** consider only for demonstrated notification and
  human-in-the-loop needs.
- **D7 — dedicated orchestrator:** consider only if GitHub plus Codex demonstrably cannot coordinate
  the required workflow.

D2 through D7 are hypotheses and evaluation points, not committed implementation requirements.
They do not authorize speculative infrastructure.

## Required-check follow-up

The stable GitHub status-check name is `Python CI / Python deterministic checks`. After the
public-readiness change is merged, synchronize `main`, change repository visibility through GitHub,
verify repository and Actions access, then configure `main` protection to require that exact check
and prevent merging when it fails. Repository visibility and protection are GitHub settings and
must not be changed implicitly by repository code.
