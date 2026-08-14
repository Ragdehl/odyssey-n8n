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
- Avoid modifying unrelated files or workflows.
- Prefer small, testable changes.
- All functions and methods must have functional docstrings that describe their domain responsibility, parameters, returned values when applicable, and relevant errors. Explain what the function does rather than narrating implementation details.
- Keep `docs/implementation/STATUS.md` current so interrupted work can be resumed safely.
- Verify every workflow before declaring it complete, and propose a Git commit only after verification succeeds.
- Never silently change the ontology schema; schema changes require an explicit proposal and normally human approval.
- Do not expose, print, commit, or store secrets or credentials in project files.
- Before making potentially destructive changes, explain what will be changed and why.
- Never delete an unmerged branch or a branch whose merge status or relationship to the completed work is uncertain.

## GitHub review workflow

Before continuing implementation on a branch that has an open Pull Request, use the repository's `odyssey-pr-feedback` skill to inspect and process review feedback.

If a review comment conflicts with another comment, the approved architecture, or a material requirement, ask the user rather than guessing.

Use `odyssey-verify-change` before declaring implementation complete or ready for review. After the user merges a Pull Request, use `odyssey-post-merge` for safe synchronization and branch cleanup. Do not require the user to copy GitHub review comments back into the terminal.
