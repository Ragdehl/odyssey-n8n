# Odyssey Platform Direction

Status: **future product/platform direction; current MVP remains deliberately smaller**.

Odyssey is intended to become a persistent knowledge layer that humans, applications, and AI agents can reuse through the same safe knowledge contracts.

```text
          humans / apps / AI agents
                    |
                    v
          trusted client/interface
                    |
                    v
+-------------------------------------------+
|                 Odyssey Core              |
| identity / schema / retrieval / mutation  |
| references / history / pending evidence   |
+-------------------------------------------+
                    |
                    v
          user/workspace knowledge
```

The key platform decision is **shared semantics, not mandatory centralized hosting**.

## Core versus interface layers

### Odyssey Core

Core owns reusable knowledge behavior:

- stable identity and canonical note semantics;
- schema validation and safe schema-extension boundaries;
- exact/semantic/contextual retrieval/resolution;
- validated create/update/delete/type migration;
- reference binding and atomic-fact semantics;
- request execution, pending evidence, and history/audit boundaries;
- future authorization hooks where a real multi-user contract requires them.

Core should not implement the UI/business workflow of every domain application.

### Interface/server adapters

A deployed interface may expose Core through HTTP, n8n, MCP, a local native adapter, or another narrow transport. The adapter owns authentication/integration/transport responsibilities appropriate to that deployment and must not become a second semantic authority.

A future hosted/self-hosted server may expose HTTP/MCP/auth/events, but MCP is one interface to Odyssey, not Odyssey itself.

### Applications

Applications provide domain UX and behavior while reusing Core identity/storage/retrieval/mutation safety. Expected families include projects/tasks, purchases/receipts, recipes, translation/workflows, real estate/home, and others discovered from real use.

Applications may contribute validated domain types/properties/guidance through a future extension boundary. They must not write arbitrary frontmatter or maintain incompatible shadow knowledge stores merely because they have their own UI.

## Zero-configuration first, extensible when useful

The default personal UX remains natural capture without requiring the user to design schema.

```text
natural request
     |
     v
reuse existing schema/identity safely
     |
     +--> ordinary facts
     +--> existing useful structure
     `--> ambiguity / future explicit schema proposal
```

A future schema coach may help propose user/app extensions conversationally, but proposal and application remain separate. Deterministic validation, collision checks, compatibility/migration behavior, and explicit approval protect the canonical schema.

## User-owned storage

Odyssey must not require canonical Markdown to live in a centrally hosted Odyssey service. The user/workspace owns the knowledge and chooses an authorized storage/deployment shape.

Possible shapes include:

```text
current self-hosted
  Raspberry/runtime + user-owned vault

future local desktop/mobile
  local Core-compatible adapter + local knowledge/indexes

future managed/shared
  trusted service + explicit storage/auth/sync contract
```

Canonical Markdown and safe Core semantics are the portable contract. The current Python/FastEmbed implementation is not itself a promise that identical binaries run on Android/iOS; a future native/mobile implementation may use different storage/inference adapters while preserving data and safety semantics.

## Local-first portability

Single-user capabilities that do not inherently require shared coordination should remain portable in principle:

- canonical knowledge storage;
- rebuildable SQLite/index projections;
- deterministic filtering/analytics;
- local semantic retrieval using a mobile-compatible inference implementation;
- identity/validation/mutation semantics.

A server is justified when the feature requires a trusted shared coordination point: real private/shared authorization, group membership, synchronized shared identity, conflict handling, cross-device events, managed hosting, or a managed AI credential relay.

Phase 20 is intentionally a **server-backed mobile web MVP**, not a decision against future local-first clients.

## External AI and client credentials

External model providers remain replaceable boundaries. Do not embed raw provider master keys in browser/mobile application code.

A future local/mobile product should use an explicitly designed safe provider-authentication/credential-relay pattern when external AI is needed—for example a user-authorized broker/gateway or another mechanism that keeps long-lived secrets out of distributable client code. Choose a concrete provider/pattern only when implementation begins; avoid freezing vendor availability/pricing claims into durable architecture documentation.

## Permissions consequence

Fine-grained private/shared authorization must occur before underlying note access and before retrieval/model exposure. If every device already receives every Markdown file, an API filter cannot provide real confidentiality over those files.

```text
identity/authentication
        |
        v
authorization / effective knowledge view
        |
        v
retrieval / LLM / application / write
```

The detailed future security/synchronization contract lives in [Multi-user Collaboration Direction](multi-user-collaboration-direction.md).

## Application routing/composition

The platform should eventually load only the selected application's detailed contract and let capabilities reuse explicit lower-level dependencies. The detailed deferred routing/composition direction is indexed in [Future Extension Points](future-extension-points.md); do not build a general plugin/package system before the first real application proves what is needed.

## Platform invariant

Odyssey may gain more clients and deployment modes, but they should continue to converge on one safe knowledge authority rather than fragmenting identity, schema, or mutation semantics across applications.
