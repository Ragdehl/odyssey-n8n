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
- Do not add infrastructure without a clear need.
- Explain important architectural trade-offs before making large changes.
- Keep components modular so they can be replaced later.
- Prefer native n8n nodes when they solve the problem cleanly.
- Use custom code only when it provides a clear advantage over native n8n functionality.
- Avoid modifying unrelated files or workflows.
- Prefer small, testable changes.
- Do not expose, print, commit, or store secrets or credentials in project files.
- Before making potentially destructive changes, explain what will be changed and why.
