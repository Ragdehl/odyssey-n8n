# Future local-first mobile runtime

Status: **future optional product phase; not a Phase 18 requirement**

## Purpose

Preserve the product direction that Odyssey's single-user knowledge Core should be able to remain useful without requiring an Odyssey-managed server, including a future Android/iOS application shape.

The intended product split is:

```text
ODYSSEY LOCAL / FREE
  |
  +--> canonical user-owned knowledge
  +--> local derived indexes
  +--> local semantic retrieval
  +--> deterministic filters / analytics
  +--> safe Core mutation semantics
  `--> optional external AI calls paid by the user

ODYSSEY CLOUD / OPTIONAL PAID
  |
  +--> shared notes / groups / permissions
  +--> synchronization and conflict handling
  +--> managed multi-device collaboration
  +--> optional managed backup
  `--> optional managed AI/credential relay
```

The free/local direction is a product goal, not a promise that the current Python implementation can be copied unchanged into a mobile application.

## What can remain local

The current architecture is deliberately compatible with a future local client because its durable and derived responsibilities do not inherently require a central server:

- canonical Markdown knowledge remains user/workspace-owned;
- SQLite indexes are derived and rebuildable rather than authoritative;
- deterministic filtering, counts, sums, grouping, and other structured analytics can execute locally;
- local MiniLM-style embedding/retrieval can be implemented with a mobile-compatible inference runtime;
- identity, validation, note mutation, reference binding, and history semantics belong to Core rather than to n8n or a hosted service.

A future mobile implementation may port/reimplement adapters or performance-sensitive components in a mobile-native stack while preserving the same contracts. Portability of the **architecture and data model** matters more than preserving Python/FastEmbed as the only implementation.

## Server is optional for the single-user Core

Do not make the Phase 18 Raspberry HTTP/runtime adapter a semantic dependency of Odyssey.

```text
                 Odyssey Core contracts
                /                      \
               v                        v
     Raspberry/self-hosted          mobile local runtime
           adapter                       adapter
               |                            |
              n8n                          app UI
```

A server becomes justified when the feature itself requires a trusted shared coordination point, especially:

- real private/shared authorization across users;
- group membership and permission enforcement;
- synchronized shared-note identity and conflict handling;
- server-side events/notifications across devices;
- a managed hosted knowledge service;
- a managed AI credential/proxy service.

Ordinary single-user filtering, local semantic retrieval, and structured analytics do not by themselves justify a server.

## External AI and credentials

A local/mobile Odyssey may still call external model APIs for the intelligent boundaries that cannot or should not run locally. The credential UX must not require embedding a user's raw provider master key inside application code.

OpenAI's current security guidance explicitly says not to deploy an OpenAI API key in client-side browser/mobile applications because the key can be extracted and abused. Therefore a future mobile product should evaluate safer provider-authentication patterns rather than treating a pasted OpenAI secret as the default consumer UX.

### Credential-broker / account-connect direction

A useful future option is a neutral AI gateway/credential broker that the user configures once and then authorizes individual applications through an OAuth-like flow.

As of 2026-09-02, OpenRouter is a concrete example worth evaluating rather than a committed Odyssey dependency:

- OpenRouter supports OAuth with PKCE so an application can send the user through an authorization flow and receive a user-controlled dedicated OpenRouter API key;
- local/localhost and headless application flows are documented;
- OpenRouter supports BYOK, storing provider keys such as OpenAI keys in the user's OpenRouter workspace and routing requests through them;
- current OpenRouter model availability includes GPT-5.6 Sol and GPT-5.6 Luna.

Conceptually this can provide the UX:

```text
user
  |
  v
one AI-provider/gateway account
  |
  +--> provider keys / credits managed there
  |
  v
"Connect Odyssey"
  |
  v
scoped/revocable application credential
  |
  v
Odyssey calls Luna / Sol / other models
```

This is close to the desired outcome of avoiding manual provider-key sharing across many applications.

However, do not adopt a gateway solely for convenience without evaluating:

- privacy/data-routing implications;
- provider and model feature parity (Structured Outputs, reasoning controls, Responses-compatible behavior, etc.);
- pricing/fees and billing ownership;
- availability and vendor dependency;
- credential revocation/limits/scoping;
- whether direct provider OAuth or a better standard becomes available later.

Other future deployment choices remain possible, including an Odyssey-managed relay, a user-self-hosted proxy, or eventually suitable local models. The provider boundary should remain replaceable.

## Candidate future phase

Treat mobile/local packaging as a **future optional phase after the real E2E and hardening work**, not as a requirement for Phase 18 or Phase 19.

A future phase would validate at least:

1. the minimum portable Core contract independent of n8n/server transport;
2. local Markdown/storage behavior under mobile filesystem constraints;
3. local SQLite/index rebuild and migration behavior;
4. on-device MiniLM-compatible embedding latency, memory, battery, and package-size cost;
5. secure device credential storage and account-connect flow for external AI;
6. offline behavior and what operations degrade when external AI is unavailable;
7. compatibility with the same canonical knowledge as desktop/self-hosted Odyssey.

Do not begin this phase merely because mobile is technically possible. Begin it when there is a concrete product reason to ship a standalone application.

## Product principle

Preserve this direction:

> Odyssey Core should be local-first and useful without an Odyssey subscription. Hosted collaboration, synchronization, managed AI, and other server-dependent capabilities may be optional paid services without making the user's basic knowledge system dependent on Odyssey Cloud.
