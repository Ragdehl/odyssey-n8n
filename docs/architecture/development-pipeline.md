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
Codex implementation + local iteration
    |
    v
GitHub PR + deterministic server-side CI
    |
    v
human review and merge
```

- GitHub owns branches, pull-request state, server-side checks, and any future merge protection or
  auto-merge policy.
- Codex owns implementation, local test iteration, feature-branch work, and Draft PR creation and
  updates.
- Agents and LLMs provide judgment; they do not replace deterministic validation.
- Pre-commit provides fast local feedback, while GitHub CI independently validates commits and pull
  requests.
- n8n remains responsible for integrations, notifications, external orchestration, and eventual
  human-in-the-loop flows when a concrete need justifies them. It is not part of development CI.

## Evolution points

- **D0 — manual stable workflow:** phase specification, Codex implementation, local verification,
  Draft PR, semantic review, and human merge.
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
