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
                ODYSSEY CORE (planned)
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

After the low-level storage layer is complete, domain logic should not be implemented as independent n8n workflows by default. Search, entity resolution and upsert, context assembly, knowledge saving, and note manipulation are planned to move into a code-based `odyssey-core`, initially Python. Odyssey Core should eventually be the normal and sole writer of knowledge notes.

This direction does not add an API or implement Odyssey Core yet. It also does not introduce LangGraph, a database, or an index.

### Odyssey Core

The planned core will own domain and note logic while preserving small, atomic or near-atomic notes with stable identity, controlled note types, human-readable content, and ordinary Obsidian wikilinks. Its detailed design belongs to later work.

### Storage layer

The current low-level n8n storage layer consists of `storage_read`, `storage_write`, and `storage_list`. Together they hide physical file handling behind a small contract. They may remain as V1 administrative, reference, or testing tools after Odyssey Core takes ownership of normal knowledge-note writes.

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
