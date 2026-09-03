# Phase 20 — Odyssey Online MVP

Status: **planned after Phase 19.2; implementation not started**

## Objective

Create the smallest standalone Odyssey experience that is useful from a phone browser when ChatGPT is not the consumer.

The product must let one authorized user submit ordinary natural-language requests from a mobile web page, reuse the existing n8n -> runtime -> Core path, and receive a conversational response grounded only in the bounded evidence returned by Odyssey.

```text
phone browser
     |
     v
Odyssey Online
     |
     v
n8n orchestration
     |
     v
Odyssey runtime -> odyssey_core.execute_request()
     |
     +--> write/result evidence
     `--> grounded retrieval evidence
                 |
                 v
          bounded answerer
                 |
                 v
        response in browser
```

This is a thin consumer/product surface, not a second knowledge system. Markdown remains authoritative and Odyssey Core remains the semantic/write boundary.

## Product constraints

- Mobile-first web before native Android/iOS development.
- Reuse the existing request/result contract instead of creating a parallel API.
- Do not expose the unauthenticated local Odyssey runtime directly to the Internet.
- Keep model/provider credentials on the trusted server/n8n side, never in browser JavaScript.
- No custom speech-to-text in the MVP. The ordinary text field is sufficient and Android users may use Gboard dictation.
- Do not add a frontend framework, database, queue, or new service unless the simplest implementation demonstrably requires it.
- Real-vault activation remains an explicit human-controlled deployment step after Phase 19 hardening; disposable data should be used for initial integration evidence.

## Phase sequence

```text
20.0  consumer contract + architecture challenge             ⬜
20.1  grounded answerer benchmark                            ⬜
20.2  minimal mobile web frontend                            ⬜
20.3  protected Raspberry/Cloudflare deployment + E2E        ⬜
```

### 20.0 — consumer contract and architecture challenge

Before implementation, run the repository architecture challenge against the actual post-19.2 runtime and n8n deployment.

Choose the smallest web-serving arrangement that preserves the existing boundaries. Prefer reusing existing infrastructure over introducing another application server merely to serve a small page. The exact web-hosting mechanism is intentionally not fixed by this planning contract because Phase 19 evidence may expose constraints that change the simplest choice.

The browser-facing contract should remain narrow:

```text
request text
    |
    v
trusted server/orchestration boundary
    |
    v
Odyssey application result
    |
    +--> deterministic acknowledgement when sufficient
    `--> grounded retrieval evidence -> answerer when conversational synthesis is needed
```

A model call is not required merely to say that a deterministic write succeeded. Use an answer model where semantic formulation of retrieved evidence materially improves the response.

### 20.1 — grounded answerer benchmark

Benchmark a small answer-generation boundary that receives only:

- the user's request;
- the public bounded Odyssey result needed to answer it;
- explicit instructions to remain grounded in supplied evidence.

Start with the existing `gpt-5.6-luna` family as the preferred inexpensive candidate because Odyssey already has positive bounded-semantic evidence for Luna in other roles. That prior evidence does **not** authorize Luna automatically as the answerer. Compare it against a suitable inexpensive alternative when available, with the current stronger Sol behavior used only as a quality reference rather than an assumed production default.

The benchmark should include at least:

- one simple single-note answer;
- multiple retrieved notes where only some evidence is relevant;
- empty retrieval / insufficient evidence;
- partial Odyssey results;
- Spanish and French requests;
- names and domain terms that occur in the retrieved content;
- a case where the model must refuse to invent a missing fact.

Evaluate correctness, unsupported claims, useful uncertainty, latency, token usage, and estimated cost. Prefer the cheapest configuration that matches the required grounded-answer quality.

Any production answer prompt/model change requires the focused live evidence and regression sentinels required by `AGENTS.md`.

### 20.2 — minimal mobile web frontend

Build only the user surface needed to exercise Odyssey naturally from a phone:

```text
+--------------------------------+
| Odyssey                        |
|                                |
| [ Ask or tell Odyssey...     ] |
|                         Send   |
|                                |
| response                       |
+--------------------------------+
```

Minimum behavior:

- one normal text input/textarea;
- submit button and sensible Enter behavior;
- loading/error state;
- render the final conversational response;
- preserve enough bounded diagnostic information for development without showing internal prompts, provider payloads, hidden reasoning, secrets, SQLite details, or raw exceptions;
- usable in Chrome on Android at phone width.

Gboard dictation is treated as normal keyboard input. Phase 20 does not implement microphone recording, browser speech APIs, transcription APIs, or stored audio.

Do not add accounts, chat-history synchronization, attachments, push notifications, PWA/offline behavior, rich Markdown editing, or native mobile packaging merely to call the MVP complete.

### 20.3 — protected deployment and real E2E

Expose the web surface through the user's existing Cloudflare setup using a separate Odyssey hostname, conceptually:

```text
n8n.ragdehl.com       -> existing n8n surface
odyssey.ragdehl.com   -> protected Odyssey Online surface
```

The exact hostname remains deployment configuration, not a Core contract.

The public Odyssey surface must be protected before it can reach personal knowledge or provider-backed actions. Prefer the smallest Cloudflare Access policy that restricts the application to the authorized user. Do not rely on an obscure URL as authentication.

Changing Cloudflare routes, Access policies, credentials, permissions, or other security boundaries requires explicit human approval under `AGENTS.md` before the deployment mutation is performed.

Initial E2E evidence should use a disposable Odyssey workspace. Activating the real personal vault is a separate explicit deployment approval after retry/failure safety and access protection are demonstrated.

## Answerer safety contract

For retrieval-oriented requests, the answerer is a renderer/reasoner over supplied Odyssey evidence, not a second retriever or knowledge authority.

It must:

- answer from supplied grounded evidence only;
- represent missing evidence explicitly rather than fill gaps from model memory;
- preserve useful distinctions between completed, partial, failed, and empty-result Odyssey outcomes;
- never mutate canonical knowledge itself;
- never receive hidden model reasoning from upstream Odyssey components;
- not require direct filesystem, SQLite, Git, or pending-work access.

The existing Phase 18 grounded consumer result remains the input boundary unless benchmark evidence proves one small additional public field is necessary.

## Acceptance criteria

Phase 20 is complete when observable evidence demonstrates all of the following:

1. an answerer benchmark selects a bounded production configuration from measured quality/cost evidence rather than assumption;
2. empty or insufficient retrieval evidence cannot produce invented factual answers in the accepted benchmark;
3. a phone browser can submit natural-language text through a minimal web interface;
4. the request reuses the existing n8n/runtime/Core execution path instead of duplicating Odyssey semantics in the frontend;
5. a retrieved Odyssey result is turned into a grounded conversational response and displayed to the user;
6. deterministic write acknowledgements do not require an unnecessary answer-model call when existing result fields are sufficient;
7. browser code contains no provider secret or raw Odyssey credential;
8. the Internet-facing surface is protected by an explicit access-control boundary before any real personal vault is enabled;
9. normal Gboard dictation works through the ordinary text field without Odyssey-specific speech infrastructure;
10. deterministic verification, required focused live model evidence, CI, semantic review, and human merge are green.

## Out of scope

Phase 20 does not authorize:

- native Android/iOS applications;
- custom speech-to-text or audio storage;
- multi-user accounts, groups, sharing, or synchronization;
- rich note browsing/editing UI;
- direct Obsidian/Markdown filesystem edit ingestion;
- retrieval-strategy redesign;
- proactive notifications/resurfacing;
- generic plugin/SDK packaging;
- replacing n8n or Odyssey Core with frontend logic.

## Future evolution

After the MVP is actually used, prioritize observed product friction. Direct Markdown/Obsidian ingestion and retrieval refinement should use those real cases rather than synthetic priority alone. A later native/local-first client remains compatible with the same Core boundaries but is not required for Odyssey Online v1.
