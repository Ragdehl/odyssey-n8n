# Odyssey platform direction

Status: **future product/platform direction; not an implementation contract**

## Purpose

Preserve the intended long-term role of Odyssey without forcing speculative infrastructure into the current single-user implementation.

Odyssey is intended to evolve from a personal knowledge application into a **persistent knowledge layer for humans, applications, and AI agents**. The current roadmap remains authoritative for implementation order; this document records the broader direction that later phases may refine after the first real end-to-end use case.

```text
                humans
                   |
                   v
applications --> Odyssey <-- AI agents
                   |
                   v
          persistent knowledge
```

The central product idea is that several clients can read and modify the same durable knowledge through one safe Core boundary instead of each application or model maintaining an isolated memory.

## Platform layers

The long-term shape should keep separate responsibilities rather than turning Odyssey Core into one large application.

```text
┌─────────────────────────────────────┐
│            Odyssey Core             │
│ identity / types / retrieval        │
│ safe writes / relations / history   │
│ pending evidence / authorization*   │
└──────────────────┬──────────────────┘
                   │
┌──────────────────▼──────────────────┐
│           Odyssey Server            │
│ HTTP API / MCP / auth* / events*    │
└──────────────────┬──────────────────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
     normal       AI       human/editor
      apps       agents      clients
```

`*` Future capability, not current implementation.

### Odyssey Core

Core owns generic knowledge behavior such as:

- stable entity identity;
- canonical note types and properties;
- exact/semantic/contextual retrieval and resolution;
- validated create/update/delete/type-migration behavior;
- relationship/reference handling;
- request-level execution and pending-work evidence;
- later authorization hooks and audit/history boundaries.

Core should not need to understand the UI or business workflow of a recipe app, project app, translation app, or real-estate app.

### Odyssey Server

The server is a deployment/interface layer around Core, not the canonical owner of the user's knowledge merely because it is a server.

It may eventually expose:

- an ordinary HTTP API for web/mobile/desktop applications;
- MCP for ChatGPT, Claude, other assistants, and autonomous agents;
- authentication/workspace boundaries for multi-user deployments;
- bounded events/webhooks where integrations require them.

MCP is therefore **one interface to Odyssey**, not Odyssey itself.

### Applications

Applications provide domain-specific UX and workflows while reusing the same Odyssey knowledge foundation.

Examples already discussed include:

```text
projects        recipes         translation       real estate
---------       -------         -----------       -----------
project         recipe          client            client
 task           ingredient      assignment        property
 idea            product         document          visit
 decision        store           quote             agent
```

An application should decide what its domain means and how users interact with it. Odyssey should provide generic identity, storage, retrieval, mutation, history, and later permissions.

A normal Android/web/desktop application would usually call an HTTP/SDK boundary. An AI assistant would usually use MCP. Both should reach the same underlying knowledge and safety rules.

## Zero-configuration first, explicit structure when wanted

For the personal product, the default experience should be **capture first, structure automatically**. A user should be able to empty their head in ordinary language without first choosing a note type, defining properties, filling a form, selecting tags, or maintaining a personal ontology.

```text
"Álex tiene dos hijos, Asi y Asae. Creo que uno tiene siete años."
                         |
                         v
                      Odyssey
                         |
             +-----------+-----------+
             |                       |
             v                       v
       existing structure      safe new knowledge
       reused/updated           prepared or clarified
```

Odyssey should map incoming knowledge to existing validated types/properties when it can do so safely. It must not invent schema merely because a sentence contains a new concept; ambiguity or a missing structural contract should remain explicit rather than silently creating arbitrary metadata.

Automatic structure is the default UX, **not a restriction on user control**. A user should eventually be able to inspect and edit structured properties directly and, through an explicit supported schema-extension flow, create custom properties or types when the built-in/domain structure does not fit their needs.

Examples might include a user deciding that they personally want:

```text
person
  met_at
  children_names

recipe
  freezer_friendly
```

Likewise, an application/domain pack may need to register its own domain structure, for example:

```text
project
  status
  deadline
  owner
```

The intended ownership hierarchy is therefore conceptually:

```text
Core schema
    |
    +--> registered domain/app extensions
    |
    `--> explicit user-defined extensions
              |
              v
        canonical note values
```

The exact schema-extension mechanism is future work. Neither an LLM nor an application may add arbitrary frontmatter fields silently. User-created and app-provided properties must eventually pass through one explicit validated extension contract covering at least ownership, namespacing/collisions, type compatibility, migrations, installation/removal where applicable, and schema validation.

The product principle is: **simple by default, structured underneath, inspectable and extensible when the user wants control.**

## User-owned and configurable knowledge storage

**Odyssey must not require canonical Markdown notes to live inside a centrally hosted Odyssey server.**

The durable knowledge belongs to the user/workspace. The physical storage location should be configurable as long as the Odyssey process has authorized access to the configured vault/storage boundary.

Possible deployment shapes include:

```text
single user
  Odyssey process + local/synced vault

self-hosted
  Odyssey on Raspberry Pi / home server
  vault on local disk, mounted disk, NAS, or supported synced storage

managed service (future)
  hosted Odyssey Server
  + explicitly chosen managed or user-controlled storage model
```

The current source-of-truth rule remains unchanged: **canonical knowledge is Markdown**, while indexes/embeddings/runtime data are derived and rebuildable.

The server may be physically colocated with the notes, but that is a deployment choice rather than a semantic requirement.

### Important consequence for permissions

Storage freedom and per-note permissions interact strongly.

If every user's device receives every Markdown file directly, an Odyssey API cannot provide real confidentiality merely by hiding unauthorized notes in search results; the user already has the files.

Therefore a future multi-user deployment with meaningful private/shared note permissions must enforce authorization **before underlying note access** and may require storage/workspace boundaries that do not distribute unauthorized files to every client.

```text
user
  |
  v
authentication
  |
  v
authorization
  |
  v
only permitted knowledge
  |
  v
retrieval / LLM / application
```

Obsidian/direct filesystem access can remain valuable, especially for single-user or fully shared workspaces, but fine-grained ACLs may require a different synchronization/access model. Do not pretend frontmatter permissions are secure when the underlying files are already readable.

## Extensibility and domain packs

The intended direction is that new applications should not require adding every domain concept directly to Odyssey Core.

Conceptually, Odyssey may later support installable/registered **domain packs** or equivalent extension contracts:

```text
Odyssey Core
    |
    +--> projects domain
    +--> recipes domain
    +--> real-estate domain
    `--> translation domain
```

A domain pack could eventually contribute a bounded set of:

- domain types;
- properties and validation rules;
- compact app-routing metadata;
- optional application-specific capabilities or writing profiles.

The exact schema-extension mechanism is **not decided**. Current ontology rules still apply: do not silently introduce types/properties or let applications mutate the canonical schema ad hoc. A future contract must define namespacing, collisions, migrations, ownership, installation/removal, and validation before domain packs become real infrastructure.

Third-party developers could eventually build applications against the HTTP API/SDK and/or MCP boundary without modifying Odyssey Core, provided their domain contract is registered safely.

## What this direction is not

This document does **not** authorize immediate implementation of:

- a cloud service;
- user accounts;
- per-note ACLs;
- domain-pack installation;
- a public SDK;
- Android/iOS/desktop applications;
- remote storage connectors;
- synchronization/conflict resolution;
- multi-tenant infrastructure;
- a generic plugin framework.

Build these only from demonstrated requirements after the first real E2E proves the core workflow useful.

## Near-term relationship to the roadmap

The implementation sequence remains:

```text
✅ 17A  executable request flow
✅ 17B  durable pending work
➡️ 17C  local Git history per request_id
⬜ 18   n8n + first real E2E
⬜ 19   hardening / tracing
```

Phase 18 is the first place where an external server/interface boundary becomes concrete. Keep that first E2E deliberately small. After real usage, reassess which platform capabilities are justified.

## Questions to resolve from E2E evidence

After Odyssey is being used end-to-end, revisit at least:

1. what the minimal HTTP/MCP server contract actually needs to expose;
2. whether the existing local filesystem vault abstraction is sufficient or needs a storage interface;
3. which deployment modes matter first: local, self-hosted, or managed;
4. what real application should become the first reusable domain extension;
5. how domain schema extensions can remain safe and reversible for both applications and explicit user-defined structure;
6. when authentication and authorization become necessary;
7. how Obsidian/direct-file access should coexist with future fine-grained permissions;
8. whether third-party SDK/app support has enough demonstrated demand to justify a public extension contract.

Until then, preserve the simple rule: **Core owns safe knowledge semantics; interfaces and applications sit above it; the user owns the canonical knowledge.**
