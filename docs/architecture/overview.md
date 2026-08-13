# Odyssey Architecture

## Purpose

Odyssey turns unstructured input into reusable personal knowledge. It starts with a small n8n-based architecture and keeps Markdown files on the Raspberry Pi as the authoritative state.

## System overview

```text
                         USER
                           |
                           v
                       ChatGPT
                           |
                    one stable Action
                           |
                           v
                     n8n Webhook
                           |
                           v
                    Odyssey Agent
                           |
                high-level domain tools
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
   save_knowledge    process_receipt    future tools
          |                |
          +--------+-------+
                   |
                   v
             ONTOLOGY CORE
                   |
     +-------------+-------------+-------------+
     |             |             |             |
     v             v             v             v
resolve_entity  upsert_entity  search      get_context
                   |
                   v
              STORAGE LAYER
                   |
       +-----------+-----------+
       |           |           |
       v           v           v
      read        write        list
                   |
                   v
           Markdown files
           on Raspberry Pi
                   |
                   v
                Obsidian
```

The names in this diagram describe intended boundaries, not an already implemented API. Exact contracts and the ontology schema will be designed and tested in later phases.

## Layer responsibilities

### User interface and stable Action

ChatGPT is the initial user-facing interface. It should call one stable Action rather than expose storage details or a large collection of internal primitives. Other interfaces may be added later without changing the knowledge model.

### n8n webhook and Odyssey agent

n8n receives the request, authenticates and routes it, and orchestrates the work. The Odyssey agent interprets intent and selects an appropriate high-level domain tool. n8n remains the orchestration platform unless an observed requirement demonstrates that it cannot handle the job simply.

### Domain workflows

Domain workflows such as `save_knowledge` and `process_receipt` translate a user goal into calls to ontology primitives. They own domain-specific validation and sequencing while sharing the same ontology core.

For example, receipt processing may resolve a store and purchased-item entities, then create or enrich a purchase note whose human-readable content links to those notes. This reuses the same primitives as general knowledge capture instead of building a receipt-specific storage model.

### Ontology core

The ontology core uses small, atomic or near-atomic notes with stable identity, a controlled note type, human-readable content, and optional ordinary Obsidian wikilinks. Linked notes form a lightweight graph, but links do not require machine-defined relation types.

The conceptual V1 core has four primitives:

- `resolve_entity` identifies the best existing note and is the main defense against duplicates.
- `upsert_entity` creates a note when necessary or enriches an existing note, including its content and wikilinks.
- `search` finds knowledge through names, aliases when supported, note types, metadata, Markdown content, and useful link information.
- `get_context` returns a note plus useful linked and backlinked context.

Separate `link_entities`, `add_fact`, and `record_event` primitives are not required in V1. Their useful behavior can initially be expressed through note content, note types, wikilinks, and `upsert_entity`. They may be introduced later if an observed requirement justifies distinct contracts.

### Storage layer

The storage layer hides physical file handling behind a small contract, initially resembling read, write, list, and—only when explicitly justified—delete. This keeps ontology logic independent of Raspberry Pi host paths and Markdown serialization details.

The physical mapping is currently:

```text
Raspberry Pi host             n8n container
/data/odyssey                 /odyssey
  vault/                        vault/
  config/                       config/
  runtime/                      runtime/
```

## Markdown as source of truth

Markdown files under `/data/odyssey` are the initial source of truth and remain readable through Obsidian and ordinary file tools. Indexes, caches, graph projections, or vector indexes may be introduced only for an observed need. Any derived representation must be rebuildable from Markdown.

Markdown and Obsidian are the human-first representation: simple readable notes, stable identity, note type, and ordinary wikilinks. A future index or LLM may provide optional machine enrichment by interpreting links, backlinks, note types, context, and text. Derived interpretations must not become required Markdown complexity unless a demonstrated requirement justifies additional structure.

A Markdown file is a physical representation of ontology knowledge, not a permanent rule that every logical object must have exactly one file. Keeping the ontology and storage contracts separate preserves room to change serialization without changing the meaning of the knowledge.

## Why agents use high-level tools

Agents should normally see domain tools rather than orchestrate many low-level ontology calls. A high-level tool provides a stable intent-level contract, centralizes validation and idempotency, reduces inconsistent call sequences, and allows the internal implementation to evolve without changing the agent interface.

Low-level primitives remain reusable building blocks for deterministic subworkflows and carefully controlled internal composition. They are not the default public surface for an agent.

## Workflow composition

```text
domain workflow
    |
    +--> validate domain input
    +--> resolve and reuse existing entities
    +--> compose ontology primitives
    +--> persist through the storage contract
    +--> return a stable result or structured error
```

Each reusable subworkflow should have an explicit input contract, output contract, error behavior, dependencies, and repeatable tests. Native n8n nodes are preferred when they express the behavior cleanly; custom code is reserved for cases where it has a clear advantage.

## Search evolution

The public `search` contract should remain stable while implementation capability grows:

1. V1: text, metadata, aliases, and wikilinks.
2. V2, if demonstrated useful: a rebuildable graph or other index.
3. V3, only if justified: semantic or vector search.

No database, vector store, framework, or additional service is required for the initial architecture.
