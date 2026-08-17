# ADR 0000: Foundational knowledge and application boundaries

- Status: Accepted (retrospective record)
- Date: 2026-08-17

## Context

Odyssey established several related boundaries before formal ADRs were introduced. They are recorded
together because they define one architecture: portable human-owned knowledge below a replaceable
application core, with orchestration at the outside. This record reconstructs only decisions visible
in the repository and rationale supplied during review; it does not assign undocumented motivations.

## Decision

Markdown files usable directly by Obsidian are the authoritative personal-knowledge source. Database
state, search indexes, caches, and model artifacts are derived and rebuildable. The application schema
is version-controlled in Git, personal notes live in the vault, and disposable operational state lives
outside both.

Normal Obsidian wikilinks are the default relationship representation. Deterministic frontmatter is
added only when a demonstrated query or process needs it. Odyssey does not require a generic typed-edge
vocabulary or redundant inverse relationships: that structure would add maintenance and synchronization
cost without a demonstrated use case.

Reusable knowledge semantics belong in the Python `odyssey_core/` package. n8n owns external integration
and orchestration rather than expressing domain primitives as many independent workflows, which would
fragment the core knowledge rules.

Within Core, representation, validation, and storage remain separate:

```text
domain and identity behavior
           |
           v
generic Note + canonical validation
           |
           v
Markdown codec
           |
           v
VaultRepository (raw filesystem boundary)
           |
           v
authoritative Markdown vault
```

`VaultRepository` performs contained raw text I/O and path listing. It does not parse Markdown or own
schema and domain behavior. The generic `Note`, Markdown codec, and canonical validator separate the
knowledge representation from its current filesystem storage.

Identity resolution is layered. Odyssey exhausts cheap deterministic evidence before semantic search;
semantic search then retrieves candidates rather than granting identity confidence. Existing-entity
possibilities must be reasonably exhausted before a create or update decision is made.

```text
exact identity evidence
        |
        v
semantic candidate retrieval
        |
        v
later contextual decision (may abstain)
        |
        v
create or update only after validation
```

## Alternatives rejected or deferred

- A database or index as a second authoritative knowledge store is rejected; derived stores must be
  reconstructible from Markdown.
- Mandatory typed relationships and inverse edges are rejected until a concrete deterministic need
  justifies the minimum additional structure.
- Domain behavior distributed across n8n workflows is rejected in favor of reusable Python behavior.
- Treating semantic similarity or rank as identity confidence is rejected. It remains evidence for a
  later decision layer.

## Consequences

Knowledge remains portable, inspectable, and usable without Odyssey. Derived infrastructure and model
components can be replaced without migrating the source of truth. Core owns consistent domain contracts,
while storage and orchestration stay narrow. The trade-off is that richer machine structure must be
derived or introduced deliberately when a real requirement appears.
