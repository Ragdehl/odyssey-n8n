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
               integration orchestration
                           |
                           v
              ODYSSEY CORE (Python)
                           |
             domain and note logic
                           |
                           v
              Markdown storage
                           |
           Markdown files
           on Raspberry Pi
                   |
                   v
                Obsidian
```

The names in this diagram describe intended boundaries, not an implemented API.

## Layer responsibilities

### User interface and stable Action

ChatGPT is the initial user-facing interface. It should call one stable Action rather than expose storage details or a large collection of internal primitives. Other interfaces may be added later without changing the knowledge model.

### n8n boundary

n8n remains part of Odyssey. Its long-term role is integrations, triggers, OAuth and credentials, scheduling, webhooks, external-service orchestration, retries, observability, and human-in-the-loop flows.

Domain logic should not be implemented as independent n8n workflows by default. Search, entity resolution and upsert, context assembly, knowledge saving, and note manipulation belong in the Python package at `odyssey_core/`. Odyssey Core should eventually be the normal and sole writer of knowledge notes.

The package now includes the filesystem-only `VaultRepository`, but it does not yet implement Markdown interpretation or domain primitives. There is no API, CLI, LangGraph, database, or index.

### Odyssey Core

The core owns the application boundary for domain and note logic, including search and entity resolution, note semantics, Markdown interpretation and serialization, normal vault access, coherence, and idempotency. It preserves small, atomic or near-atomic notes with stable identity, controlled note types, human-readable content, and ordinary Obsidian wikilinks. `odyssey_core/storage/` owns safe raw-text filesystem access. Markdown parsing, serialization, schema validation, updates, and domain behavior remain separate later-layer responsibilities.

### Storage layer

The current low-level n8n storage layer consists of `storage_read`, `storage_write`, and `storage_list`. They remain available as V1 administrative, reference, or testing tools. Odyssey Core's `VaultRepository` is the normal Python filesystem boundary and is intended to support the Core eventually becoming the sole normal writer of knowledge notes.

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

Each reusable n8n subworkflow should have an explicit input contract, output contract, error behavior, dependencies, and repeatable tests. Native n8n nodes are preferred when they express integration and orchestration behavior cleanly; custom code is reserved for cases where it has a clear advantage.

## Search evolution

The public `search` contract should remain stable while implementation capability grows:

1. V1: text, metadata, aliases, and wikilinks.
2. V2, if demonstrated useful: a rebuildable graph or other index.
3. V3, only if justified: semantic or vector search.

No database, vector store, framework, or additional service is required for the initial architecture.
