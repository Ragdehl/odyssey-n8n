# Phase 20 — Odyssey Online MVP

Status: **Phase 20.0 consumer contract and architecture challenge complete on merge; Phase 20.1 next**

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
- Reuse the existing request/result contract instead of creating a parallel semantic API.
- Do not expose the unauthenticated local Odyssey runtime directly to the Internet.
- Keep model/provider credentials on the trusted server/n8n side, never in browser JavaScript.
- No custom speech-to-text in the MVP. The ordinary text field is sufficient and Android users may use Gboard dictation.
- Keep frontend source in `odyssey_web/` in this repository, separate from Core and runtime responsibilities.
- Do not add a frontend framework, database, queue, or new long-lived service unless the simplest implementation demonstrably requires it.
- Real-vault activation remains an explicit human-controlled deployment step; disposable data should be used for initial integration evidence.

## Phase sequence

```text
20.0  consumer contract + architecture challenge             ✅ complete on merge
20.1  grounded answerer benchmark                            ➡️ next
20.2  minimal mobile web frontend                            ⬜
20.3  protected Raspberry/Cloudflare deployment + E2E        ⬜
```

## 20.0 — consumer contract and architecture challenge

### Architecture challenge

Result: **PROCEED**.

The actual problem is not to build another knowledge service. Odyssey already has the semantic and persistence path required by the product. The missing responsibility is a narrow single-user consumer that can:

1. accept one natural-language request from a phone browser;
2. preserve delivery identity across an uncertain client retry;
3. send the request through the existing n8n -> runtime -> Core path;
4. turn the typed result into either a deterministic UI acknowledgement or a grounded conversational answer;
5. return a small browser-safe response.

The post-Phase-19 boundaries already solve most of the hard work:

- n8n owns external orchestration and already delegates Odyssey execution rather than duplicating Core semantics;
- the host runtime is a thin internal HTTP adapter around `execute_request()` and remains serial/fail-simple;
- Core owns planning, retrieval, mutation, pending work, Git history, and canonical Markdown rules;
- the Phase 18 consumer result already exposes bounded grounded retrieval evidence;
- Phase 19 preserves delivery-owned `request_id` and adds bounded operational evidence retained by n8n executions.

A second application server, public runtime endpoint, frontend database, event bus, or new tracing layer would duplicate existing responsibilities without evidence of need.

### Adopted browser/server shape

The browser-facing trusted boundary is **n8n**, not the local Odyssey runtime.

```text
phone browser
     |
     | HTTPS (protected in 20.3)
     v
Odyssey Online n8n surface
     |
     +--> GET: minimal mobile page
     |
     `--> POST: {request, request_id}
                |
                v
        existing runtime /execute
                |
                v
           Odyssey Core
                |
                v
       typed ApplicationResult
                |
                +--> deterministic UI result
                `--> bounded answerer when useful
```

The target deployment is one same-origin Odyssey web surface so the MVP does not need permissive CORS, browser-held provider credentials, or a separate API client secret. Cloudflare routing and Access are deployment concerns for 20.3 and are not changed by 20.0.

The checked-in frontend source belongs under `odyssey_web/`. Phase 20.2 should use the smallest way to serve that source through the adopted n8n-facing web surface. It must not introduce a second long-lived application server merely to serve a small static page. The exact packaging/injection mechanism for the static asset is an implementation detail to validate in 20.2; if n8n cannot consume the checked-in asset cleanly without hand-maintained duplication, reconsider only the static-serving mechanism, not the API/Core boundary.

The existing development `odyssey-runtime` workflow remains an internal execution bridge. Phase 20 should add a separate Odyssey Online workflow/surface rather than turning the development workflow or the Python runtime into the public product endpoint.

### Delivery identity

The browser generates one safe `request_id` before the first submission and reuses that exact ID if it retries the same uncertain delivery. n8n forwards it unchanged to the runtime.

Conceptually:

```text
new user submission
   -> request_id = web-<random id>
   -> POST

response lost / explicit retry of same submission
   -> SAME request_id
   -> POST again

new user submission
   -> NEW request_id
```

`request_id` is correlation/idempotency identity only. It is not authentication or authorization. A browser implementation may keep a pending ID only long enough to make an explicit retry safe; Phase 20 does not require durable browser history.

Do not add automatic retries that generate a fresh ID for the same uncertain delivery.

### Browser request contract

The product request is intentionally narrow:

```json
{
  "request": "ordinary natural-language text",
  "request_id": "web-..."
}
```

Rules:

- `request` must be non-empty ordinary text;
- `request_id` must satisfy the existing bounded safe identifier contract;
- no chat history, model prompt, provider configuration, filesystem path, vault credential, or client-side authority is accepted from the browser;
- every submission is semantically independent in the MVP; conversational history/synchronization is not introduced implicitly.

### Server-side routing contract

After n8n receives the typed Odyssey result, it chooses the cheapest safe presentation path. This routing is product composition, not Core semantics.

```text
transport/runtime failure
    -> deterministic error UI

ApplicationStatus.FAILED
    -> deterministic failure UI

completed retrieval with zero grounded items
    -> deterministic "insufficient Odyssey evidence" UI

write-only result
    -> deterministic acknowledgement/status UI

retrieval with grounded items
    -> bounded answerer

mixed write + retrieval
    -> bounded answerer for retrieved evidence
       + deterministic mutation status
```

A model call is therefore not required merely to say that a deterministic write succeeded, that no Odyssey evidence was found, or that execution failed.

A partial result with grounded retrieval evidence may still use the answerer, but the answerer receives the partial status and must not imply that incomplete work succeeded. The UI may additionally show a deterministic partial-status notice.

### Answerer boundary

The answerer remains outside Odyssey Core and outside canonical persistence. It is a renderer/reasoner over supplied public evidence, not a retriever or knowledge authority.

The answerer receives only the minimum consumer projection needed to answer:

- the user's current request;
- overall completed/partial status needed for honest wording;
- retrieval query/action identity when useful;
- grounded retrieved items with stable `id`, canonical `type`, human-readable `content`, and vault-relative `path` provenance.

It does **not** receive merely for answer generation:

- prompts or hidden reasoning from upstream models;
- Git details;
- pending-work records;
- operational/tracing metadata;
- provider payloads or credentials;
- SQLite or filesystem access;
- unrestricted exception details.

Phase 20.1 selects the production answer model/configuration from benchmark evidence. No model is adopted by 20.0.

### Browser response contract

The browser does not need the full `ApplicationResult`. n8n returns a narrow product result shaped conceptually as:

```json
{
  "request_id": "web-...",
  "status": "completed | partial | failed",
  "kind": "answer | acknowledgement | empty | error",
  "message": "human-facing text"
}
```

Additional fields require a demonstrated UI need. In particular, the browser does not receive raw provider usage, Git history, pending records, prompts, raw exceptions, or retrieved evidence merely for debugging.

Development diagnosis uses the returned `request_id` to inspect the normal n8n execution and Phase 19 operational evidence server-side. This is sufficient to preserve diagnosability without widening the browser contract.

### UI/repository boundary

The planned repository shape remains:

```text
odyssey-n8n/
├─ odyssey_core/        # canonical semantic/domain logic
├─ odyssey_runtime/     # internal n8n -> Core adapter
├─ odyssey_web/         # mobile web source only
├─ workflows/           # n8n orchestration/product HTTP surface
└─ docs/
```

`odyssey_web/` must not read Markdown, SQLite, Git, pending work, or provider credentials and must not contain planner/retrieval/write logic. It knows only the browser request/response contract.

### Security boundary

20.0 does not mutate Cloudflare, n8n security, credentials, network routes, or the real vault.

20.3 must protect the Odyssey hostname with an explicit access-control boundary before the public web surface can reach provider-backed actions or personal knowledge. Keep the existing n8n administration hostname logically separate from the Odyssey product surface. Do not rely on an obscure webhook path as authentication.

The browser API should remain same-origin and JSON-only; do not add permissive cross-origin access merely for convenience.

Actual Cloudflare route/Access changes and real-vault activation require explicit human approval under `AGENTS.md`.

### 20.0 acceptance result

20.0 is complete on merge when the repository records all of the following:

- the architecture challenge result is `PROCEED`;
- n8n is the trusted browser/orchestration boundary;
- the Python runtime stays internal and thin;
- `request_id` retry ownership is explicit at the browser boundary;
- answerer routing distinguishes deterministic acknowledgement/empty/error paths from semantic answer generation;
- the answerer input projection is bounded and grounded;
- the browser response is narrower than the raw `ApplicationResult`;
- frontend source remains isolated under `odyssey_web/`;
- no new long-lived service, database, queue, or security mutation is introduced.

## 20.1 — grounded answerer benchmark

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

The benchmark harness and deterministic fixtures can be prepared without the Raspberry, but production model adoption requires focused live provider evidence using the exact candidate configurations. Any accepted production answer prompt/model change must also satisfy the focused live evidence and regression-sentinel rules in `AGENTS.md`.

## 20.2 — minimal mobile web frontend

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
- generate one stable request ID per new submission and reuse it for an explicit retry;
- loading/error state;
- render the final conversational response or deterministic acknowledgement/empty/error state;
- retain only the current interaction state needed by the page; no synchronized chat history;
- usable in Chrome on Android at phone width.

Gboard dictation is treated as normal keyboard input. Phase 20 does not implement microphone recording, browser speech APIs, transcription APIs, or stored audio.

Do not add accounts, chat-history synchronization, attachments, push notifications, PWA/offline behavior, rich Markdown editing, or native mobile packaging merely to call the MVP complete.

## 20.3 — protected deployment and real E2E

Expose the web surface through the user's existing Cloudflare setup using a separate Odyssey hostname, conceptually:

```text
n8n.ragdehl.com       -> existing n8n administration/orchestration surface
odyssey.ragdehl.com   -> protected Odyssey Online surface
```

The exact hostname remains deployment configuration, not a Core contract.

The public Odyssey surface must be protected before it can reach personal knowledge or provider-backed actions. Prefer the smallest Cloudflare Access policy that restricts the application to the authorized user. Do not rely on an obscure URL as authentication.

Changing Cloudflare routes, Access policies, credentials, permissions, or other security boundaries requires explicit human approval under `AGENTS.md` before the deployment mutation is performed.

Initial E2E evidence should use a disposable Odyssey workspace. Activating the real personal vault is a separate explicit deployment approval after access protection and disposable E2E evidence are demonstrated.

## Answerer safety contract

For retrieval-oriented requests, the answerer is a renderer/reasoner over supplied Odyssey evidence, not a second retriever or knowledge authority.

It must:

- answer from supplied grounded evidence only;
- represent missing evidence explicitly rather than fill gaps from model memory;
- preserve useful distinctions between completed, partial, failed, and empty-result Odyssey outcomes;
- never mutate canonical knowledge itself;
- never receive hidden model reasoning from upstream Odyssey components;
- not require direct filesystem, SQLite, Git, or pending-work access.

The existing Phase 18 grounded consumer result remains the source boundary unless benchmark evidence proves one small additional public field is necessary.

## Acceptance criteria

Phase 20 is complete when observable evidence demonstrates all of the following:

1. an answerer benchmark selects a bounded production configuration from measured quality/cost evidence rather than assumption;
2. empty or insufficient retrieval evidence cannot produce invented factual answers in the accepted benchmark or production routing;
3. a phone browser can submit natural-language text through a minimal web interface;
4. one logical browser delivery preserves its request ID across an explicit retry;
5. the request reuses the existing n8n/runtime/Core execution path instead of duplicating Odyssey semantics in the frontend;
6. a retrieved Odyssey result is turned into a grounded conversational response and displayed to the user;
7. deterministic write acknowledgements, empty retrievals, and ordinary failures avoid unnecessary answer-model calls;
8. browser code contains no provider secret or raw Odyssey credential;
9. the Internet-facing surface is protected by an explicit access-control boundary before any real personal vault is enabled;
10. normal Gboard dictation works through the ordinary text field without Odyssey-specific speech infrastructure;
11. deterministic verification, required focused live model evidence, CI, semantic review, and human merge are green.

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
