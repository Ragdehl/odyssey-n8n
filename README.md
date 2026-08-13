# Odyssey

## What it is

Odyssey is a personal knowledge system and a reusable foundation for future applications. It transforms unstructured information into reusable, human-readable knowledge while keeping personal Markdown files authoritative.

The system is intentionally simple. Additional structure and infrastructure should appear only when concrete use cases justify them.

## Core principles

- Markdown is the source of truth for personal knowledge.
- Notes are atomic or near-atomic, with stable identity and controlled note types providing the minimum useful structure.
- Ordinary Obsidian `[[wikilinks]]` are the default relationship mechanism.
- Structured properties are added only when deterministic processing requires them.
- Derived indexes, caches, and databases must remain rebuildable rather than authoritative.
- Prefer the simplest working architecture.

See [Ontology Principles](docs/architecture/ontology.md) for the authoritative knowledge-model guidance.

## High-level architecture

```text
User
  ↓
ChatGPT
  ↓
stable Custom GPT Action
  ↓
n8n webhook
  ↓
Odyssey Agent
  ↓
domain workflows / knowledge primitives
  ↓
Markdown on Raspberry Pi
  ↓
Obsidian
```

ChatGPT provides the conversational and reasoning layer. n8n and Odyssey provide deterministic orchestration, tools, and storage boundaries. See the [Architecture Overview](docs/architecture/overview.md) for responsibilities and intended component boundaries.

## Repository and data boundaries

This Git repository contains code, application configuration and schema, tests, Codex skills, architecture documentation, and future version-controlled workflows.

`/data/odyssey` is separate from Git. It contains authoritative personal Markdown knowledge and rebuildable runtime data. See [Local Storage Boundary](docs/architecture/storage.md) for the precise ownership and path model.

## Current status

The foundational architecture and local storage boundary are complete. The simplified ontology and canonical note schema are established, and reusable Codex development workflows are in place.

See [Implementation Status](docs/implementation/STATUS.md) for the current phase, verification state, and next action.

## Repository guide

- [AGENTS.md](AGENTS.md) — project rules for agents and contributors.
- [Architecture Overview](docs/architecture/overview.md) — high-level system architecture.
- [Ontology Principles](docs/architecture/ontology.md) — knowledge-model principles.
- [Canonical Note Schema](docs/architecture/note-schema.md) — how the note schema works.
- [Machine-readable note schema](config/note-schema.json) — canonical schema definitions.
- [Local Storage Boundary](docs/architecture/storage.md) — repository, personal-data, and runtime boundaries.
- [Implementation Status](docs/implementation/STATUS.md) — current implementation status.
- [Codex project skills](.codex/skills/) — reusable development workflows.
