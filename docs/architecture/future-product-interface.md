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

Detailed usage/token/cost semantics are owned by [Future Odyssey product usage observability](future-product-usage-observability.md). Conversation-context/history semantics are owned by [Future Odyssey help and conversation context](future-help-and-conversation-context.md). User-to-self-note identity is owned by [Future user self-identity binding](future-user-self-identity.md). Events/calendar semantics are owned by [Future Events / Calendar capability](future-events-calendar.md). This document owns the product/navigation direction that combines persistent chat, notes, changes, applications, and advanced surfaces.

## Approved visual interaction contract — icon-first Odyssey controls (October 2026)

Action buttons across Odyssey should use the product's existing, visually consistent
line icons rather than visible words such as `Elegir`, `Cancelar` or `Guardar`.
Preserve descriptive `aria-label` and `title` text for accessibility, tooltips and
discoverability. Icons must communicate distinct actions without relying on color alone;
focus and touch targets must remain usable on mobile. Information-bearing content
(names, note-type distinctions, grounded evidence and written chat replies) **is not**
an icon button and must remain readable. Do not strip meaningful written form labels,
option names or explanatory status messages under this rule.

Identity clarification options belong in compact rows, not large nested cards.
Display the candidate name and a concise, readable evidence preview; if
multiple options share the same evidence, show it only once instead of repeating
it under every candidate. Keep the full evidence available through the linked note. Offer the existing icon-only
choose/check, open-note and cancel controls with explicit accessible names.
An icon action must not bypass the guarded clarification and human choice flow.
Apply the same icon-first design when adding or revising other action controls;
audit legacy text-only action buttons incrementally rather than silently changing
unrelated workflows in a small UX fix.

The chat flow's compact clarification regression is covered by
`tests/odyssey_web_app.test.mjs`; all action visuals must continue using the
shared `actionButton`/`setActionIcon` primitives in `odyssey_web/notes.js`.

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
     +--> Events / Calendar
     +--> Projects
     `--> Shopping / other selected capability
```

The user-facing rules should stay simple:

- **normal chat is enough** — the user should not need to choose an app before asking for something;
- an optional explicit mention such as `@Tasks` may direct a request when the user wants control or disambiguation, but mentions must never be required for ordinary use;
- an app-specific focused entry point may exist when a capability needs one, but it must reuse the same knowledge, identity, and application state rather than becoming a silo;
- a response may carry a small capability label such as `Tasks` so the user understands what acted, without inventing separate personalities or making the product feel like a room full of independent agents;
- composition remains internal when useful: a project may use Tasks, while both Tasks and Events may use Reminders, without requiring the user to hop between app screens.

The first real application should be **Tasks**. Its implementation should prove the smallest practical application manifest/routing/state contract rather than introducing a generic plugin platform first. Once that works, **Events / Calendar** is the next prioritized application area because time-aware personal behavior is unusually valuable in ordinary Odyssey use. **Reminders** should remain the lower-level notification/delivery capability used where Tasks or Events need it. **Projects** remains a committed consumer of Tasks, but it can follow the calendar path and the bounded maintainability checkpoint rather than blocking Events. See [Future Events / Calendar capability](future-events-calendar.md).

Full message threads and branching chat management are not committed product directions. Evaluate a
capability-specific surface only when a concrete need cannot be met through the main conversation
and canonical knowledge.

The near-term executable routing/composition contract is now owned by [Application Boundary + Router v0](application-boundary-router-v0.md); longer-horizon marketplace/platform direction remains indexed by [Future Extension Points](future-extension-points.md#application-routing-and-composition) and [Odyssey Platform Direction](odyssey-platform-direction.md#application-routingcomposition).

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

Do not implement browser editing as an independent CRUD store or expose unrestricted raw Markdown as
the normal editing surface. Decide from real use how structured fact/property editing and
conversational correction should share the same Core operations.

The intended Notes authoring direction now includes three concrete product needs observed in grouped
Notes use:

- each active user-visible type group should eventually create a new Note of that type from a direct
  `+` entry point; legacy compatibility-only types should not remain permanently exposed as ordinary
  creatable types in the final catalog;
- the type information panel should eventually edit that type's user-facing description and
  configurable properties through a structured authoring surface, optionally assisted by a bounded
  conversational helper rather than requiring raw schema editing;
- an open Note should eventually allow manual editing of ordinary user-editable properties. System
  identity/provenance fields such as stable ID, creation/update provenance and timestamps remain
  non-editable, and application-owned lifecycle fields remain protected unless their owning
  application exposes an explicit safe mutation contract.

Grouped Notes may expose non-mutating work-in-progress controls for those future paths before their
Core/schema mutation contracts exist; they must never simulate a successful write.

Issue #134's future fact edit/delete, multi-select deletion, explicit `@` binding, and stable-ID
rename must reuse the Core mutation, stale-write and staged-clarification boundaries proposed in
[Semantic set resolution and evidence](semantic-set-resolution-and-evidence.md). UI-4 remains a
later product stage: no direct Notes mutation behavior is approved by that design challenge.

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

The first sequence should favor the most useful everyday surfaces while proving the application model incrementally:

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
Events / Calendar — prioritized time-aware capability
        |
        v
Reminders — only the delivery semantics Tasks / Events actually need
        |
        v
bounded maintainability checkpoint
        |
        v
Projects / UI-3 Activity / UI-4 editing / UI-5 analytics
ordered by real usage and validation needs
```

This is a product roadmap, not fixed phase numbering. Real usage may justify moving one item earlier. The first application is intentionally scheduled before building every remaining UI surface: Tasks is a concrete way to validate application routing/composition without prematurely building a general plugin system. Events / Calendar then exercises the same extension boundary against a distinct time-aware domain before Odyssey pauses for bounded structural cleanup. Durable conversation storage serves ordinary chat continuity; a later capability surface must earn its own product case. The [Functional Roadmap](functional-roadmap.md) remains the canonical owner of current status and ordering.

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
10. whether a concrete capability ever needs a specialized surface beyond the main conversation;
11. the product-wide localization contract: one language switch must translate navigation, controls,
    help/onboarding copy, type/property presentation and validation messages without changing
    canonical schema semantics or stored knowledge;
12. the exact note-type authoring UX: structured form first, conversational assistant first, or a
    hybrid, and which schema changes remain admin/advanced-only.

### DEV request execution graph — October 2026

The existing per-message information affordance now opens a dark, accessible,
mobile-first directed execution graph: original user message → Router → exact
validated routed spans → actual per-route Temporal / Tasks / Planner / Core stages
→ status and affected-note count. Two or more independent preparation branches
are visually forked; the legend explicitly says that model preparation may overlap
but canonical Core application remains ordered. Each recorded stage shows only
available model, reasoning setting, provider-call count, duration, input/output/
cached/reasoning tokens and **priced stage estimate** derived from a dated runtime
pricing snapshot. A non-LLM Core/Git stage has no invented model, tokens or cost.

Runtime attaches bounded, actor-local `execution_flow` provenance only after
Router's exact-span validation. It contains no prompts, provider payloads, hidden
reasoning or new knowledge authority. Grounded Temporal source→ISO mappings are
emitted only when Temporal actually resolved them. The workflow projects a strict
allowlist onto the existing `request_detail`, while the conversation store and
browser revalidate it. Older turns without a trace show a clearly labeled linear
fallback based solely on their recorded stages. The prior technical details are
retained collapsed under a disclosure control. Stage estimates can legitimately be
unavailable. This work changes diagnostics/presentation only and does not modify
Router, Temporal or Core semantics or execution scheduling.

The October 8 enriched trace adds typed, bounded **semantic execution evidence**
from the same validated Core plan and its actual write results: each route displays
the exact text its Planner received, the requested operation and target, the first
planned fact, read-only resolved identity mappings (e.g. a relational mention
`mi hija → Cloe` only when the stable ID is grounded against current canonical
Markdown), and applied-unit outcomes. The resolver never guesses a display name
from planner prose or opaque IDs. A missing mapping is labeled unavailable. Each
branch keeps its original text, Temporal date normalization, planning and execution
nodes; Router explicitly identifies no-split versus split, and icons make the
stages easier to scan on mobile. This is **presentation-only**: no independent
identity authority, extra model invocation, mutation, or change to route selection.
If the bounded projection fails, Core must complete unchanged and simply omit it.
Past messages without trace metadata cannot be reconstructed retroactively.

The October 8 mobile follow-up found a presentation gap, not a Router failure: the
user opened a stored pre-trace response whose actual Router stage took 5802 ms.
That historical `request_detail` contained no `flow`, so a linear fallback was
correct but omitted the original user message and looked like the new feature
had failed. The chat now associates the original user turn to its assistant
response by the durable request ID (including paginated history) and shows this
source text even for historical replies. It never fabricates the original
splitting, Temporal normalization or entity decisions if none were recorded.
For traced requests, the fork, route columns and join share one horizontally
scrollable viewport on narrow screens so branches remain distinct and readable
instead of being squashed or stacked. All diagnostic icons use real stroked SVGs
in the Odyssey style rather than platform-dependent emoji glyphs. This is a
presentation-only change requiring no extra route, network permission or AI call.
Regression checks cover legacy original-text recovery, history pagination, a
two-branch horizontal graph, SVG nodes and existing operational telemetry.

Regression: `tests/odyssey_web_request_flow.test.mjs`,
`tests/odyssey_web_app.test.mjs`, `tests/runtime/test_runtime_routing.py`,
`tests/odyssey_workflow_partial.test.mjs` and the conversation detail contract.

### 2026-10-08 — validated input/output for each routed stage

The per-message graph now persists an optional bounded `steps[]` for **each
validated Router route**. Each step is correlated in exact order with the real
`OperationalStage` and stores three plain-text fields: `name` (actual stage),
`input` (bounded semantic input), and `output` (bounded **validated** result).
Router input is the exact captured request and output is the verified route list;
Tasks input is its own split text and output is the typed lifecycle operation;
Temporal input is the source date expression and output its exact resolved date;
Planner input is the routed text plus available validated Temporal evidence,
output the typed requested operation/target/first fact; Core input is the
validated plan and output the completed/deferred/failed canonical unit outcomes
and grounded entity links. Git/pending steps only show their recorded statuses.
Unknown or failed steps explicitly have **no validated structured output**,
not a fabricated model response. A previously recorded route trace without
`steps[]` remains readable using the older display, so this is additive and
requires no migration of canonical vault data or past conversations.

This **does not** persist provider prompts, raw JSON responses, hidden reasoning,
private indexes or unbounded diagnostics. Stage strings are capped (input 512,
output 768), list length matches actual observed stage count (at most 16), and
the workflow, conversation store and browser validate the same shape. Only the
actor-owned existing per-message `request_detail` persists this projection; it
is excluded from all planning context. There is no new service, public route,
model invocation, change to identity authority, or mutation semantics.

Test sentinels cover parallel route stages and actual Core day writes, exact
Temporal source-to-ISO display, Tasks interpretation, Router split/no-split,
workflow round-trip, bounded/mismatched step rejection, durable local
conversation replay and the legacy fallback. Next: measure the parallel Core
planner path with this more inspectable evidence, without interpreting summed
stage durations as actual wall time saved.

### 2026-10-08 — multi-route diagnostic overflow and lost browser acknowledgement

A real DEV incident exposed a cross-boundary mismatch: three- and four-route
calendar writes committed their canonical Git changes, while the browser showed
a generic red failure and no info button. The existing n8n `safeOperational`
replaced the **entire** operational stage list when it exceeded 16 entries, but
still attached the independently allowed route graph. The browser correctly
refused this structurally inconsistent optional diagnostic, inadvertently
suppressing the already completed response and its conversation persistence.
This was not a reason to repeat the writes.

The per-request bound is now 64 stage records (with the original per-route bound
of 16 and max 8 routes). n8n correlates every validated route's stages with
its bounded operational list and omits the graph if it cannot be trusted. The
canonical product response is never downgraded merely because optional
observability is unavailable. The browser validates optional telemetry
strictly, but on rejection substitutes an empty **explicitly invalid** trace
marker rather than hiding a valid write result. Client/network errors also
expose a diagnostic `(i)` explaining uncertainty; they never claim that no
notes were written or automatically replay the request.

Regression tests execute the **actual** workflow stage-serialization helpers,
not mock implementations: 22 stages/four routes, 65-stage overflow fallback,
real browser product validation, persisted 22-stage conversation detail, and
both client-only failure states. No prompts, credentials, canonical notes,
mutation scheduling, or Cloudflare settings are modified.
