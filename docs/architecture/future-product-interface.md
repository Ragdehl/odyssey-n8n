# Future Odyssey product interface

Status: **preserved product direction; sequence after the protected MVP should be driven by real use and development/staging evidence**.

## Goal

Evolve Odyssey Online from a chat-only MVP into a small, understandable product surface without creating a second knowledge authority or exposing developer internals to ordinary users.

The chat remains the primary interaction surface. Additional views should use progressive disclosure:

```text
ordinary user
    -> simple chat + useful change feedback + note access

advanced/admin/developer
    -> bounded request diagnostics + usage/cost analytics
```

Canonical Markdown remains the source of truth. Git, request traces, usage evidence, and indexes are supporting history/diagnostic state, not alternate note stores.

Detailed usage/token/cost semantics are owned by [Future Odyssey product usage observability](future-product-usage-observability.md). Conversation-context/history semantics are owned by [Future Odyssey help and conversation context](future-help-and-conversation-context.md). User-to-self-note identity is owned by [Future user self-identity binding](future-user-self-identity.md). This document owns the product/navigation direction that combines persistent chat, notes, changes, applications, and advanced surfaces.

## Proposed product shape

A useful mobile-first navigation target is:

```text
Chat | Notes | Activity
             |
             `-- Usage / Diagnostics only when authorized
```

Exact tabs, names, and placement remain product decisions. Do not add navigation merely to mirror internal architecture.

## Interface roadmap

### UI-0 — persistent main conversation and resume

The first durable chat product is deliberately one ordinary conversation, not a chat manager.
Opening Odyssey restores the authenticated actor's visible chronological main transcript; the user
continues naturally without choosing a topic, opening a chat, or creating a new one. The stable
internal `conversation_id` and request correlation remain implementation details of the durable
non-canonical state contract.

```text
open Odyssey -> restore main transcript -> continue natural conversation
```

Recent visible turns may provide continuity to the planner, but canonical Markdown remains authority
for current facts and normal retrieval/mutation. The browser is never the durable authority.
Conversation list/new/open, titles, topic splitting, and deletion/export policy are not committed
product directions or UI-0 acceptance requirements. Historical transcript search is likewise not a
memory roadmap; any such feature would need separate product justification. See the current [UI-0
contract](ui-0-durable-conversations.md).

### UI-1 — request-level feedback in chat

#### Approved first implementation slice

The first UI-1 slice keeps the normal chat visually clean: an eligible response may show only a
small secondary information affordance, and activating it opens a request-specific mobile bottom
sheet that is closed by default and easily dismissed. The sheet is a reusable request-detail surface;
it is not a permanent technical block or developer console. The initial implementation is isolated
DEV work using the existing protected product boundary as the single-user advanced/admin gate. It
does not introduce multi-user RBAC, a new endpoint, persistence, analytics infrastructure, or a
second tracing authority.

The response projection may expose only reliable bounded evidence already present in the real
`ApplicationResult`/runtime contract: total and stage latency, ordered stages, safe model/reasoning
metadata, provider-call records and allowlisted usage, safe outcomes/errors, and write changes
derived from affected stable-note/unit evidence. Missing fields are omitted or unavailable. Retrieval
note content, prompts, hidden reasoning, raw provider payloads, credentials, and inferred execution
paths remain excluded.

Make each response explain enough about what Odyssey did without turning the bubble into a developer console.

For ordinary users, a write can show a compact change receipt such as:

```text
La información se ha guardado.

2 notas modificadas
Marta   updated
Thales  created
```

The affected-note summary should be derived from the real request/application result and stable note identities. It must not infer or fabricate mutations from the natural-language answer.

A response bubble may also show a visually secondary estimated cost when reliable request-level usage and dated pricing evidence exist, for example:

```text
                                     ~$0.003
Odyssey: Marta trabaja en Thales.
```

Cost represents the whole logical request, not only the final answerer call. Exact cost/token/model behavior belongs to the observability contract.

For an authorized advanced mode, tapping the request detail may expose a compact execution path such as:

```text
Planner       Luna / low
Resolver      Luna / medium x2
Writer        deterministic
Answerer      Luna / none
-------------------------------
2,180 tokens | ~$0.003 | 1.4 s
```

This is safe stage/model metadata, not hidden chain-of-thought. The existing request-level operational evidence should be reused rather than adding a second tracing system.

#### Early testing priority — advanced per-request inspector

During the first real-use period after production/development isolation is in place, treat the advanced per-request inspector as an early testing aid rather than waiting for a full analytics dashboard. The user should be able to open the detail for an individual chat response and inspect, when reliable evidence exists:

- estimated total logical-request cost;
- total and allowlisted provider token counters;
- ordered execution stages/capabilities actually traversed;
- model + reasoning configuration at each provider-bearing stage;
- number of contextual-resolver/provider invocations where distinguishable;
- whether bounded Sol fallback was used;
- total/stage latency and safe outcome/error category;
- safe integration/deployment provenance when relevant, including whether the active n8n product workflow matches the expected version-controlled source (`MATCH | DRIFT | UNKNOWN`).

The purpose is to spot abnormal real-use behavior while using Odyssey normally, for example a trivial request that costs much more than comparable requests, repeated resolver calls, an unexpected Sol fallback, one stage dominating latency, or a correct runtime result being transformed incorrectly by a stale integration workflow. The inspector must report observed bounded evidence, not infer an execution path from the final answer, and must never reveal hidden chain-of-thought, raw prompts, unrestricted provider payloads, credentials, or unrelated personal content.

This early inspector can remain advanced/admin-only even if a small cost cue is later shown to ordinary users. A full dashboard and final chart selection remain later decisions driven by accumulated real telemetry.

### UI-2 — read-only Notes view

Add a user-facing browser over the same canonical Odyssey knowledge:

- search and browse notes;
- open one note in a readable rendered view;
- expose useful metadata/links only when it helps the user;
- navigate from a chat change receipt directly to the affected note;
- treat the current user's own canonical `person` note like every other ordinary person note for search/statistics/history, while optionally presenting a small `Tú`/`You` cue derived from the stable self-identity binding rather than from a special note type or hidden profile copy.

Example:

```text
Notes
----------------
Marta
Thales
Lyon
Proyecto Odyssey

> Marta
  trabaja en [[Thales]]
  vive en [[Lyon]]
```

The first Notes view should be read-only. It must not create a second database or silently rewrite Markdown for presentation convenience.

### Application interaction — automatic by default, explicit when useful

Applications/capabilities should feel like parts of Odyssey rather than a set of bots the user must manage. The primary interaction remains an ordinary Odyssey conversation: the user speaks naturally, Odyssey selects the relevant capability, and only the selected capability executes/responds. Do not have every installed application inspect every message or compete to answer.

```text
user message
     |
     v
Odyssey routing
     |
     +--> Tasks
     +--> Projects
     `--> Shopping / other selected capability
```

The user-facing rules should stay simple:

- **normal chat is enough** — the user should not need to choose an app before asking for something;
- an optional explicit mention such as `@Tasks` may direct a request when the user wants control or disambiguation, but mentions must never be required for ordinary use;
- an app-specific focused entry point may exist when a capability needs one, but it must reuse the same knowledge, identity, and application state rather than becoming a silo;
- a response may carry a small capability label such as `Tasks` so the user understands what acted, without inventing separate personalities or making the product feel like a room full of independent agents;
- composition remains internal when useful: a project may use Tasks, and Tasks may use Reminders, without requiring the user to hop between app screens.

The first real application should be **Tasks**. Its implementation should prove the smallest practical application manifest/routing/state contract rather than introducing a generic plugin platform first. If that works well, **Projects** should follow and reuse Tasks; **Reminders** should then provide the lower-level time/reminder capability where justified. The existing architectural direction remains `Reminders <- Tasks <- Projects`.

Full message threads and branching chat management are not committed product directions. Evaluate a
capability-specific surface only when a concrete need cannot be met through the main conversation
and canonical knowledge.

The detailed executable routing/composition contract remains owned by [Future Extension Points](future-extension-points.md#application-routing-and-composition) and [Odyssey Platform Direction](odyssey-platform-direction.md#application-routingcomposition).

### UI-3 — Activity / "what changed" view

Provide a history centered on user requests and canonical mutations, correlated by `request_id` and existing Git/request evidence.

A useful default is human-readable rather than raw Git output:

```text
Hoy 13:42
"Marta trabaja en Thales y vive en Lyon"

Created: Thales
Updated: Marta
+ trabaja en [[Thales]]
+ vive en [[Lyon]]
```

Progressive disclosure should offer three levels when evidence exists:

1. **summary** — which notes were created/updated/deleted;
2. **change detail** — the relevant human-readable Markdown/fact change;
3. **raw Git diff / commit details** — advanced/developer view only.

Raw Git diff should not be the default user explanation. It is implementation-shaped, can include frontmatter/noise, and is harder to understand than a note-level change receipt. The exact canonical Git diff remains valuable for audit/debugging and should stay reachable for authorized advanced users.

A request should link both ways where practical:

```text
chat response -> request/activity -> affected note
affected note -> relevant history/request
```

### UI-4 — safe note editing

After read-only browsing and change visualization are stable, allow authorized users to edit canonical notes from the Odyssey interface.

The edit path must preserve the same authority/safety rules as other Odyssey writes:

```text
open canonical note
      |
      v
edit / preview
      |
      v
validate + conflict check
      |
      v
show proposed diff
      |
      v
canonical Markdown write
      |
      v
Git/request history + index refresh
```

Do not implement browser editing as an independent CRUD store. Decide from real use whether simple direct text editing, structured field editing, or conversational correction is the best first editor.

External Obsidian/filesystem edits remain a related but separate ingestion direction.

### UI-5 — role-aware Usage / Diagnostics dashboard

Once enough real request evidence exists, expose a protected advanced/admin surface. Candidate charts and metrics include:

- requests per day/week/month;
- estimated spend over time;
- tokens over time;
- spend/tokens by model;
- spend by capability/application when attribution exists;
- Luna-only vs Luna + Sol-fallback share;
- latency trends;
- safe failure/clarification rates;
- projected month-end spend when enough evidence exists.

Example:

```text
September
Requests        214
Est. spend    $1.84
Sol fallbacks      3

Cost by model
Luna  █████████████  $1.21
Sol   ██████         $0.63
```

Do not decide exact charts before real usage shows which questions are useful. Ordinary users should not be forced into technical telemetry. Multi-user authorization must prevent one user from inspecting another user's private request evidence.

## Suggested sequencing after the protected MVP

The first sequence should favor features that make Odyssey simpler to use while proving the application model incrementally:

```text
UI-1 request feedback + advanced request drill-down
        |
        v
UI-0 durable main conversation + one-pass continuity foundation
        |
        v
UI-2 read-only Notes
        |
        v
Tasks — first real application + minimum routing/manifest/state contract
        |
        v
Projects — reuse Tasks
        |
        v
Reminders — lower-level time/reminder capability where justified
        |
        v
UI-3 Activity / UI-4 editing / UI-5 analytics
ordered by real usage and validation needs
```

This is a product roadmap, not fixed phase numbering. Real usage may justify moving one item earlier. The first application is intentionally scheduled before building every remaining UI surface: Tasks is a concrete way to validate application routing/composition without prematurely building a general plugin system. Durable conversation storage serves ordinary chat continuity; a later capability surface must earn its own product case.

## Product principles

- Keep the chat simple by default; use drill-down instead of persistent technical clutter.
- The user should normally speak naturally; automatic capability selection is the default and explicit `@App` routing is optional.
- Do not make all applications listen to every message; select only the capability needed for the request.
- Capability-specific entry points, if justified, are not separate knowledge silos.
- Show what Odyssey actually did from durable evidence, not what the answer text merely claims it did.
- Prefer human-readable change summaries before raw Git diffs.
- Keep note browsing/editing on the canonical Markdown/Core boundary.
- Reuse `request_id`, `conversation_id`, Git correlation, application results, and existing operational evidence.
- Never expose hidden reasoning, raw prompts, secrets, unrestricted logs, or unrelated personal content in diagnostics.
- Add role-aware surfaces only when the authorization model can enforce them.
- Build charts from useful retained evidence; do not create a new analytics platform just to render graphs.

## Deferred product decisions

Decide with real Odyssey usage:

1. whether per-message cost is always visible, optional, or advanced-only;
2. whether ordinary users should see tokens at all;
3. exact mobile navigation (`Chat / Notes / Activity`, drawer, or another compact pattern);
4. exact placement/visual treatment of capability labels and any justified capability-specific surface;
5. whether change receipts live inside the assistant bubble, immediately below it, or in a linked activity panel;
6. which level of diff is useful to ordinary users versus advanced users;
7. which note-editing mode should come first;
8. which usage graphs deserve a permanent dashboard;
9. exact roles/permissions for advanced diagnostics once Odyssey becomes multi-user;
10. whether a concrete capability ever needs a specialized surface beyond the main conversation.
