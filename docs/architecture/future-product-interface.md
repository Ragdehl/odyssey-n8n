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

Detailed usage/token/cost semantics are owned by [Future Odyssey product usage observability](future-product-usage-observability.md). Conversation-context/history semantics are owned by [Future Odyssey help and conversation context](future-help-and-conversation-context.md). This document owns the product/navigation direction that combines persistent chat, notes, changes, and advanced surfaces.

## Proposed product shape

A useful mobile-first navigation target is:

```text
Chat | Notes | Activity
             |
             `-- Usage / Diagnostics only when authorized
```

Exact tabs, names, and placement remain product decisions. Do not add navigation merely to mirror internal architecture.

## Interface roadmap

### UI-0 — persistent conversation history and resume

The chat surface should behave like a durable messaging product rather than a transient form. Closing/reopening Odyssey must not make prior visible conversations disappear.

Target user experience:

```text
Chats
----------------
Hoy
  Nora Vidal
  Proyecto Odyssey

Ayer
  Ideas para el jardín

[open conversation]
        |
        v
previous visible turns remain available
        |
        v
continue the same conversation
```

Requirements:

- show a list/history of the user's prior Odyssey conversations when durable conversation records exist;
- reopening a conversation restores the visible user/Odyssey turns in chronological order;
- continuing an old conversation reuses its stable `conversation_id` rather than inventing a disconnected thread;
- a new-chat action starts a new conversation identity explicitly;
- titles/grouping may be simple and derived initially (for example first meaningful request + date); do not require a title-generation LLM just for this;
- timestamps and basic session boundaries should remain visible enough for the user to orient themselves;
- browser `localStorage` may cache presentation state, but it must not become the sole durable authority for conversation history;
- the durable source for visible chat history should reuse the non-canonical conversation records defined by the conversation/history contract, correlated through `conversation_id` and `request_id`;
- deleting/retaining/exporting conversations is a later policy decision and must not silently delete canonical personal knowledge that may have been created from those conversations.

This is a product-view requirement over the same conversation-history boundary, not a reason to make conversations canonical personal notes. The exact WhatsApp-like presentation can evolve, but **chat persistence across page/app reopen is a committed requirement**.

### UI-1 — request-level feedback in chat

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
- navigate from a chat change receipt directly to the affected note.

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

The first sequence should favor features that help validate Odyssey while it is still young:

```text
20.3B protected route
20.3C disposable E2E
20.3D real-vault activation
        |
        v
separate production from development/staging
        |
        v
UI-1 request feedback + advanced request drill-down
        |
        v
UI-0 durable chat history/resume + conversation continuity foundation
        |
        v
UI-2 read-only Notes
        |
        v
UI-3 Activity / change visualization
        |
        +--> UI-5 usage dashboard as real telemetry accumulates
        |
        `--> UI-4 note editing after read/change safety is proven
```

This is a product roadmap, not fixed phase numbering. Real usage may justify moving one item earlier. In particular, bounded advanced diagnostics may be useful early during testing even if the ordinary-user surface remains minimal; durable conversation storage may also become the enabling substrate for UI-0 and conversational context work.

## Product principles

- Keep the chat simple by default; use drill-down instead of persistent technical clutter.
- Show what Odyssey actually did from durable evidence, not what the answer text merely claims it did.
- Prefer human-readable change summaries before raw Git diffs.
- Keep note browsing/editing on the canonical Markdown/Core boundary.
- Reuse `request_id`, Git correlation, application results, and existing operational evidence.
- Never expose hidden reasoning, raw prompts, secrets, unrestricted logs, or unrelated personal content in diagnostics.
- Add role-aware surfaces only when the authorization model can enforce them.
- Build charts from useful retained evidence; do not create a new analytics platform just to render graphs.

## Deferred product decisions

Decide with real Odyssey usage:

1. whether per-message cost is always visible, optional, or advanced-only;
2. whether ordinary users should see tokens at all;
3. exact mobile navigation (`Chat / Notes / Activity`, drawer, or another compact pattern);
4. whether change receipts live inside the assistant bubble, immediately below it, or in a linked activity panel;
5. which level of diff is useful to ordinary users versus advanced users;
6. which note-editing mode should come first;
7. which usage graphs deserve a permanent dashboard;
8. exact roles/permissions for advanced diagnostics once Odyssey becomes multi-user.
