# Odyssey

Odyssey is a personal knowledge system.

## Goal

The system receives unstructured information and transforms it into atomic Markdown notes.

Each note should represent one entity, concept, idea, person, place, project, or other item with its own identity.

Notes can link to other notes.

A single input may result in:
- creating one note
- creating several related notes
- updating existing notes
- creating links between notes

## Current architecture

For now:
- n8n handles orchestration and workflows
- `odyssey_core/` is the Python application/domain core
- Markdown files are the source of truth
- LLM APIs may be used for extraction, classification, reasoning, and note generation
- external interfaces and input channels will be decided later

Do not introduce LangGraph, databases, vector databases, additional services, or new infrastructure unless they solve a concrete problem that cannot be handled simply with the current architecture.

## Development principles

- Prefer the simplest working solution.
- Understand the real requirement before increasing architectural complexity, and propose a simpler alternative when appropriate.
- Ask the user when a material requirement is ambiguous rather than guessing.
- Do not add infrastructure without a clear need.
- Do not introduce infrastructure merely because it may be useful someday.
- Explain important architectural trade-offs before making large changes.
- Document significant architecture decisions when they are made.
- When documenting workflows, architecture, decision flows, or component interactions, include a concise text/ASCII diagram when it materially improves understanding or recall. Prefer simple structural or flow diagrams; omit decorative or redundant diagrams when prose is clearer.
- Keep components modular so they can be replaced later.
- Prefer reusable subworkflows with clear input and output contracts.
- Prefer native n8n nodes when they solve the problem cleanly.
- Use custom code only when it provides a clear advantage over native n8n functionality.
- Put new Odyssey domain and note logic in `odyssey_core/` by default; use `workflows/` for n8n integration and orchestration behavior.
- Avoid modifying unrelated files or workflows.
- Prefer small, testable changes.
- All functions and methods must have functional docstrings that describe their domain responsibility, parameters, returned values when applicable, and relevant errors. Explain what the function does rather than narrating implementation details.
- Write production Python for a human reader: add concise concrete examples to non-trivial functions when they materially clarify inputs, outputs, or transformations, but omit them from trivial accessors and tests where they add noise.
- Add production-code comments when security reasoning, parsing state, or a transformation is not obvious. Comments should explain purpose or intent rather than restating the syntax.
- Use Ruff for Python linting and formatting, and pytest as the official Python test runner. New tests should normally use native pytest style; preserve existing unittest tests and migrate them only when functional work already requires modification.
- Use Git branches, commits, Pull Request state, tests, and architecture documentation as the source of project-development state.
- Verify every workflow before declaring it complete or ready. Verification must pass for completion or readiness, but a safe checkpoint commit may be made after a failure when it is clearly marked as such.
- Never silently change the ontology schema; schema changes require an explicit proposal and normally human approval.
- Do not expose, print, commit, or store secrets or credentials in project files.
- Before making potentially destructive changes, explain what will be changed and why.
- Never delete an unmerged branch or a branch whose merge status or relationship to the completed work is uncertain.

## Development autonomy and confirmation

On a feature branch, proceed autonomously with routine, reversible actions that are in scope for the approved task. This includes repository edits and tests; repeated test or validator iterations; development/test n8n workflow creation, execution, inspection, restart, and straightforward review fixes; isolated disposable fixtures and non-destructive probes; routine retries; commits and pushes to the current feature branch; and creating or updating a Draft Pull Request. Multiple n8n executions, probes, fixtures, or test iterations do not by themselves require confirmation, and an explicitly in-scope Odyssey development workflow is not sensitive merely because it is live.

Ask before actions with material data, security, architecture, or irreversibility risk: modifying or deleting real personal data in `/data/odyssey/vault`; destructive migrations with unclear rollback; deleting Docker volumes or resetting databases; destructive changes to important live workflows; credential, secret, OAuth-scope, permission, filesystem, network, or other security-boundary changes; new services or significant infrastructure; material architecture changes outside the approved scope; force-pushes or destructive Git history rewrites; direct pushes to `main`; merging a Pull Request; or material product/contract ambiguity that cannot be inferred safely.

Routine implementation risk means proceed autonomously; material data, security, architecture, or irreversibility risk means ask. A failed final verification means the work is not ready or complete, not that it should be discarded. Preserve coherent, reviewable implementation on the feature branch and record failed checks or blockers in a commit or Draft Pull Request when useful. Remove only disposable fixtures or probes, generated junk, secrets, unsafe changes, and clearly abandoned experiments.

## GitHub review workflow

## Significant functional-phase checklist

For a significant functional phase, read the canonical [Functional Roadmap](docs/architecture/functional-roadmap.md) rather than reconstructing phase state from chat or agent memory. Read the relevant architecture documents and ADRs before changing a contract, define the phase contract under the [Development Pipeline](docs/architecture/development-pipeline.md), and run the architecture challenge before implementation.

Prefer the simplest architecture and challenge unnecessary complexity. Keep one canonical source for each project fact or contract; link to it elsewhere instead of duplicating it. Implement code and tests together, review both code and documentation for correctness and stale information, and update roadmap or ADR status only when actual project state changes. Readiness requires deterministic verification and CI, followed by PR, semantic/human review, and human merge.

Before beginning each significant new functional Odyssey phase, use the repository's `odyssey-architecture-challenge` skill as a reasoning checkpoint before implementation. It is not required for tiny bug fixes, straightforward review feedback, formatting, documentation typo fixes, routine test corrections, or post-merge cleanup.

Before continuing implementation on a branch that has an open Pull Request, use the repository's `odyssey-pr-feedback` skill to inspect and process review feedback.

If a review comment conflicts with another comment, the approved architecture, or a material requirement, ask the user rather than guessing.

Use `odyssey-verify-change` before declaring implementation complete or ready for review. After the user merges a Pull Request, use `odyssey-post-merge` for safe synchronization and branch cleanup. Do not require the user to copy GitHub review comments back into the terminal.
