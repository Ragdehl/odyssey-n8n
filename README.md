# Odyssey

Odyssey is a personal knowledge system and a reusable knowledge foundation for applications and AI agents. It turns natural-language input into durable, inspectable Markdown knowledge while keeping the user's files authoritative.

The product principle is simple: **capture freely, preserve identity, add structure only when it unlocks useful behavior, and retrieve grounded knowledge when it matters.**

## Current architecture

Odyssey Core is independent from any one conversational client. The current standalone MVP uses a mobile web surface; ChatGPT or another reasoning client may also consume Odyssey through an integration boundary.

```text
mobile browser / reasoning client
              |
              v
      trusted integration layer
              |
             n8n
              |
              v
     thin Odyssey runtime
              |
              v
        odyssey_core/
   planning / retrieval / writes
              |
       +------+-------+
       |              |
       v              v
canonical Markdown   derived state
/data/odyssey/vault  SQLite/indexes/cache
```

For Odyssey Online, the browser talks to n8n; the internal Python runtime is not exposed directly to the Internet. n8n owns external integration/orchestration, while `odyssey_core/` owns reusable knowledge, identity, validation, retrieval, and mutation behavior.

## Knowledge model

- Markdown is the source of truth for personal knowledge.
- One logical entity normally has one stable note identity.
- Ordinary knowledge accumulates as append-first atomic facts inside that note.
- Ordinary Obsidian `[[wikilinks]]` are the default relationship representation.
- Types and structured properties exist only when they enable repeatable user-facing behavior such as filtering, comparison, calculation, reminders, or application logic.
- SQLite indexes, embeddings, caches, and other runtime projections are derived and rebuildable.
- Ambiguity fails closed rather than silently attaching knowledge to the wrong identity.

See [Odyssey Knowledge Model](docs/architecture/knowledge-model-direction.md) and [Canonical Note Schema](docs/architecture/note-schema.md).

## Current product stage

Odyssey has completed the first real n8n/Core end-to-end path and its reliability hardening. The current phase is **Phase 20 — Odyssey Online MVP**:

```text
20.0  consumer contract                                  ✅
20.1A grounded-answerer benchmark preparation            ✅
20.1B focused live answerer evidence                     ➡️ next
20.2A mobile web source + offline checks                 ✅
20.2B real n8n serving + Chrome Android validation       ⬜
20.3  protected Raspberry/Cloudflare deployment + E2E    ⬜
```

The canonical current status and later work live in the [Functional Roadmap](docs/architecture/functional-roadmap.md).

## Repository and data boundaries

The Git repository contains code, tests, versioned workflow definitions, schema/configuration, development skills, and project documentation.

- `odyssey_core/` — Python application/domain core.
- `workflows/` — reviewable n8n Workflow SDK definitions.
- `odyssey_web/` — minimal mobile web client source.
- `config/note-schema.json` — machine-readable canonical note schema.
- `benchmarks/` — frozen model/retrieval evidence and evaluation harnesses.
- `docs/` — durable product, architecture, infrastructure, and decision documentation.

Personal and operational data remain outside Git under `/data/odyssey`; see [Local Storage Boundary](docs/architecture/storage.md).

## Documentation map

Use a small set of documents as the entry points:

- [AGENTS.md](AGENTS.md) — project and agent-development rules.
- [Product Vision](docs/product-vision.md) — durable product promise and safety principles.
- [Architecture Overview](docs/architecture/overview.md) — current system boundaries and request flow.
- [Functional Roadmap](docs/architecture/functional-roadmap.md) — canonical implementation status and next work.
- [Odyssey Knowledge Model](docs/architecture/knowledge-model-direction.md) — current knowledge representation principles.
- [Canonical Note Schema](docs/architecture/note-schema.md) — interpretation of `config/note-schema.json`.
- [Local Storage Boundary](docs/architecture/storage.md) — authority and filesystem/runtime ownership.
- [Development Pipeline](docs/architecture/development-pipeline.md) — how significant changes are specified, implemented, verified, and reviewed.
- [Future Extension Points](docs/architecture/future-extension-points.md) — index of intentionally deferred product/architecture directions.
- [Architecture Decisions](docs/decisions/README.md) — accepted historical ADRs and measured decisions.

Phase documents, ADRs, and benchmark records preserve **historical contracts and evidence**. They may describe the project as it existed at that checkpoint; they are not the source of current phase status unless the roadmap links them as the active contract.

## Development philosophy

Prefer the smallest working architecture. Do not add a service, database, framework, model stage, schema field, or workflow merely because it may be useful later. New complexity should solve a demonstrated problem and preserve the authority boundaries above.
