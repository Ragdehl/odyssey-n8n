# UI-2 — read-only Notes product contract

Status: **the bounded reliability correction introduced at `044d6c9` is deployed in isolated DEV and the
subsequent authenticated reliability checkpoint passed. A final recovery-control presentation correction
is deterministically verified and READY FOR THE FINAL UI-2 CLOSEOUT CHECK; Draft PR #124 remains NOT
READY FOR MERGE until that check passes. The first authenticated mobile checkpoint failed because the n8n static workflow omitted
reachable `notes.js` / `notes-client.js` modules, so `app.js` never bootstrapped, and CSS allowed the
hidden Notes view to stack below Chat. The correction makes Chat and Notes mutually exclusive
application-level views, moves Notes search to the mobile bottom interaction zone, adds a
schema-capability-driven filter sheet, derives/serves the complete local module graph, and adds
deployment/browser regression guards. The second checkpoint rendered the corrected layout but still
could not bootstrap because the DEV tunnel retained the old seven-path contract; its DEV-only
ten-path inventory is now shared by deployment validation and the public-route preflight. The third
checkpoint confirmed the basic product is usable (exclusive Chat/Notes, feed, filters, sort, details,
links/backlinks infrastructure, and public bootstrap), and exposed the closure items now addressed:
empty canonical bodies, planner-backed explicit Notes search, visible inferred filters,
human-readable Markdown/link/backlink presentation, complete type cues, and historical affordances
in older Chat pages. Direct isolated-DEV runtime/n8n/static evidence is `MATCH` at commit `03d644c`;
the mounted assets, zero-provider local query/detail path, and explicit intelligent-operation
transport pass. Python CI and Sonar are green at 83.6% new-code coverage. One production Luna→Sol
planner case passed within the $0.15 hard live-gate budget before the next case was safely stopped.
All public routes remain Access-gated; production ingress, Access, CSP, DNS, origin, and fallback
remain unchanged. A later authenticated write exposed one final reliability defect: same-ID retries
could rerun a multi-note plan, and the serial runtime made Notes/conversation reads unavailable while
the write ran. The bounded correction and evidence are recorded below. Its deterministic suite is
green (`962 passed`, `79 skipped`, `52 subtests passed`), the isolated DEV deployment has matching
source/workflow/public-route provenance, and direct runtime health, Notes capabilities, conversation
reload, and mounted browser commit checks pass. UI-2 is not complete in PROD.**

## Long-write reliability closure

The 2026-09-21 authenticated DEV incident crossed three previously separate assumptions:

```text
browser sends request ID
        |
        v
serial runtime executes Core --------------> canonical mutation + Git commit
        |                                      (result not durably replayable)
        v
n8n returns product result
        |
        v
browser persists assistant turn
```

The initial user turn was durable before planning, but the assistant turn belonged to a later browser
request. Losing the product response therefore left an unmatched user turn. Retry preserved the ID,
but the runtime had no whole-result ledger and planned again. Correlation by that ID found three
overlapping n8n executions and three substantive Git commits under the same request trailer. While
the serial runtime processed them, queued Notes calls reached the workflow's exact 30-second timeout
and a conversation call reached its exact 10-second timeout. The first runtime result itself completed
in about 91.4 seconds (planner 57.9 seconds, action 27.4 seconds, index refresh 4.9 seconds), so the
evidence does not identify the configured 120/125-second product deadlines as the first-response
failure; it establishes a lost browser delivery after a completed backend result.

The correction preserves the synchronous product and conversation ownership contracts:

- the HTTP adapter is concurrent, while `RuntimeComposition` retains a single product-execution lock
  around planner/mutation/Git/index work;
- a completed mutation response is atomically stored in actor-local durable state before HTTP
  delivery and replayed for the same request fingerprint, including after runtime reconstruction;
- a conflicting request under the same ID, corrupt record, or unsafe identity fails closed;
- the result record contains no request text and is not available to retrieval or planner continuity;
- transcript reload recognizes only a newest unmatched user turn and offers an explicit
  `Recuperar resultado` action with its original ID; it never retries automatically;
- a dropped assistant-turn persistence call therefore remains recoverable without replanning or
  mutating canonical knowledge again.

The effective timeout inventory remains intentionally unchanged: browser product fetch 125 seconds;
n8n private runtime request 120 seconds; Notes request 30 seconds; conversation request 10 seconds;
answerer 60 seconds; planner SDK read timeout 600 seconds; contextual resolver, fact selector, and
writer 120 seconds each; no runtime application deadline; Cloudflare's documented default proxied
origin read timeout 125 seconds. The isolated DEV n8n container has no overriding execution-timeout
environment setting. Latency/model tuning remains post-UI-2 work.

Deterministic evidence pauses a synthetic write with synchronization events and proves health, Notes,
and conversation reads return before it is released. Separate tests cover pre-result retry, a
duplicate arriving while the original is running, restart-safe completed-result replay, request-ID
rebinding/corruption, exactly one Core execution, conversation continuity failure, and explicit reload
recovery. No provider call or real-vault mutation is required for this gate.

The subsequent authenticated reliability check confirmed that Chat/Notes reads remain available during
a long write and that reload recovers the completed logical result without repeating its mutation. It
exposed only a presentation defect: the recovery notice and its action were separate global nodes,
leaving stale text after success. The browser now mounts one recovery component inside the specific
unmatched user turn, shows `Recuperando…` while replay is pending, restores its action on a retryable
failure, and removes the complete component before rendering the recovered assistant turn. The final
human closeout check is therefore intentionally narrow: verify that this inline recovery presentation
remains coherent on the authenticated DEV surface.

## Objective

Add a clean mobile-first **Notes** surface over the same canonical Odyssey Markdown so the user can
browse, search, filter, open, and navigate knowledge directly without creating a second knowledge
authority or requiring the user to understand Odyssey internals first.

UI-2 should teach the structure of Odyssey progressively through ordinary use: note type, properties,
tags, links, backlinks, and filtering should become understandable because they are visible and useful,
not because the user must complete a tutorial before using the product.

The product remains deliberately simple:

```text
Odyssey
  |
  +--> Chat
  `--> Notes
```

The first Notes phase is read-only. Canonical Markdown remains authoritative.

## Primary navigation

Use a small, persistent top-level selector/navigation at the top of the product surface for the
current two primary Odyssey views:

```text
+-----------------------------+
|      Chat        Notes      |
+-----------------------------+
|                             |
|          content            |
|                             |
+-----------------------------+
```

Chat and Notes are two primary views of the same Odyssey product, not independent applications. The
bottom edge remains available for surface-specific interaction, especially the Chat composer. Do not
turn the selector into one tab per future application or design Calendar/Tasks navigation in UI-2.
If actual product growth eventually justifies a different global navigation model, reconsider it
from observed use rather than speculating now.

Switching surfaces must preserve each surface's local interaction state:

- Chat keeps its current scroll position and unsent draft;
- Notes keeps its current query text, active filters, sort, loaded result state, navigation history,
  and currently open note;
- returning to either surface resumes where the user left it rather than resetting to a default view.

## Notes home: relevant knowledge feed

The Notes landing surface is not grouped by note type and is not alphabetically ordered. It is a
scrollable/paginated feed of notes ordered by a cheap deterministic notion of **current relevance**.

Each row/card should expose enough structure to be useful without becoming visually dense. The
initial product direction is:

```text
[type icon] Note title
            compact useful note information
            updated recently
```

The note type should be recognizable at a glance through a small consistent icon and a restrained
color token. The visual system should be coherent across the feed, filters, note view, and rendered
links. Avoid an uncontrolled rainbow of full-text colors.

The default relevance order should be deterministic and inexpensive. Candidate signals include:

- recent note update/activity;
- recent user interaction/use where reliable local evidence already exists;
- connections to recently active knowledge;
- a small structural-connectivity contribution.

Pure backlink/link count must not dominate ranking: a historically central note should not remain at
the top forever merely because it has many old connections. The exact deterministic rule is recorded
under [Ranking and pagination](#ranking-and-pagination); it is not a hidden model judgment.

The feed must load incrementally rather than deserialize/render the whole vault. Scrolling downward
loads subsequent pages while preserving a smooth visual position, analogous to the bounded loading
already proven for durable chat history.

## Type icons and colors

The product requirement is a small, simple, stable icon plus restrained color per note type. Emoji are
useful for documentation examples but should not be the production dependency because platform emoji
rendering differs across Android, iOS, browsers, and desktop environments.

A likely implementation shape to challenge later is:

```text
canonical note type id
        |
        v
presentation map
  -> SVG/icon token
  -> color token
        |
        v
feed / filters / note view / wikilinks
```

The canonical note schema continues to define **semantic note types and their properties**. Visual
presentation metadata should not be silently added to `config/note-schema.json`. The resolved
architecture keeps icon/color presentation in a small UI map and leaves the canonical schema
unchanged.

For inline links, prefer the type icon/color as the visual type cue while keeping link text visually
consistent. Color the entire linked text only if DEV visual validation shows that it remains calm and
readable rather than producing a rainbow effect.

## Search: one field, two execution modes

The Notes search field supports two complementary behaviors.

### 1. Immediate local text search while typing

As the user types, update results locally without provider/model calls. Exact/canonical title matches,
lexical/text matches, and existing cheap local indexes should respond quickly enough to feel like a
normal search box.

The query text remains in the field after results appear so the user can edit/refine it without
retyping the original search.

### 2. Explicit intelligent search

An explicit AI affordance (for example a small sparkle/star action) executes the full Odyssey-style
intelligent search only when the user requests it. This path should reuse existing Odyssey retrieval,
semantic evidence, schema, and validated planning capabilities as far as the architecture allows
rather than creating an independent search stack.

The output of Notes search is **a ranked set/list of notes**, not a prose answer. Chat remains the
surface for synthesis/explanation.

Useful mental model:

```text
while typing
  -> local lexical/exact search

press intelligent-search action
  -> semantic/structured Odyssey search
  -> ranked notes + visible filters
```

Search relevance should prioritize the active query. Existing retrieval scores/evidence may be reused
only as specified under [Ranking and pagination](#ranking-and-pagination); not every internal score is
a comparable product ranking.

## Filters

Filters are first-class Notes state. Keep common filters easy to reach while placing advanced filters
in a compact mobile bottom sheet or similarly lightweight progressive-disclosure surface.

### General filters

At minimum, support/filter architecture for common note metadata such as:

- note type;
- tags;
- creation date/range;
- update date/range.

Creation/update dates should be available for filtering and sorting without forcing both dates onto
every feed card. The default card may show update recency because it is usually more useful for
current relevance; both dates can be visible in the note detail view.

### Type-specific filters

Once the user selects a note type, expose the properties declared for that type by the canonical note
schema. UI controls should follow the property kind when practical, for example:

- date/date-time -> exact value or range;
- integer -> exact value or bounded range;
- controlled string -> select/multi-select;
- array string such as tags/aliases -> chips or exact multi-value selection;
- ordinary string -> exact textual value/list according to the existing filter contract.

The note schema is the semantic source for what properties exist. The UI must not maintain an
independent hand-written copy of type properties. A future kind such as boolean, enum, free-form
number, or note reference must first become a supported shared Core filter capability; UI-2 does not
invent a browser-only operator for it.

### AI-inferred filters

When intelligent search can safely interpret part of the request as structured filters, show those
filters explicitly as editable/removable chips. Example:

```text
query:  people related to Airbus in Toulouse
chips:  [Person x] [City: Toulouse x]
```

After creation, query text and filter chips are **independent state**. Editing/removing words from the
query does not silently remove an already-visible filter. The user can remove a chip explicitly or
clear the whole search state. This avoids invisible/magical coupling and also teaches the user what
Odyssey understood.

## Sorting

Default sort is **Relevance** using the deterministic feed/search rules above. Provide a compact sort
control for at least useful chronological alternatives such as:

- Relevance;
- Recently updated;
- Recently created;
- Oldest created where useful.

Alphabetical order is not the primary product order.

## Note detail view

Opening a note renders a human-readable view over canonical Markdown; it is not an editor in UI-2.

The view should include:

- note title;
- visible note type icon/color cue;
- a bounded set of properties presented in human-readable labels/values;
- tags;
- creation/update dates where useful;
- rendered canonical body content;
- clickable links to other Odyssey notes;
- backlinks (`Enlazada desde` / equivalent localized label).

Do not show raw YAML/frontmatter by default. Frontmatter-backed information should be rendered as
ordinary product UI.

### Property disclosure

Show only a small bounded number of properties initially so a type with many fields does not overwhelm
the note. Initial target: **up to six visible properties**. If more exist, offer `Ver todas las
propiedades` / equivalent expansion.

For the initial implementation, choose which properties appear first using the existing order in the
canonical note schema rather than inventing a separate importance model. A future presentation-priority
concept can be proposed only if real use demonstrates the need.

## Note-to-note navigation

Rendered internal links should behave like web/wiki links. A link opens the target note, and the user
can navigate backward and forward through the note-navigation history.

The inline link should include the target note's small type icon when resolvable. A restrained type
color cue may accompany it; full linked-text type coloring remains subject to visual validation.

Multiple simultaneously open note tabs are explicitly deferred for UI-2 mobile. They may be useful on
tablet/desktop later, but nested tab systems should not complicate the first mobile Notes experience.

## Backlinks

UI-2 includes **explicit backlinks only**. Do not add semantic/embedding-derived `related notes` in
this phase.

The backlinks section should expose notes that demonstrably link/reference the current note. A useful
row contains:

- source note type icon;
- source note title, clickable;
- one compact context/snippet showing the mention/fact where practical;
- number of additional mentions if more than one exists;
- an expansion affordance when additional context is available.

The desired product order is **most recently active/referenced first**. UI-2 uses the source note's
canonical `updated_at` as the reliable activity chronology, as specified under
[Backlinks and chronology](#backlinks-and-chronology). Do not confuse `happened_at` with
capture/update/Git chronology, and do not invent fact timestamps that Odyssey does not currently own.

## Chat -> Notes result sets

Chat should distinguish between a request for a **set of notes** and a request for **synthesized
knowledge**.

Examples:

```text
"Show me all people I know in Toulouse"
    -> result set / Notes link

"What relationship do the people I know in Toulouse have with Airbus?"
    -> Chat retrieval + grounded synthesis

"Explain the relationship and show me the notes"
    -> Chat answer + Notes result-set link
```

For a result-set request, avoid reading/synthesizing every matching note merely to enumerate them in
chat. Chat should return a compact result-set affordance such as `Ver 18 notas`, and the user chooses
whether to open Notes. Do not automatically switch surfaces after every such request; preserve user
control unless a later explicit product contract says otherwise.

Opening the result-set affordance takes the user to Notes with the corresponding query/filter state.

## Durable historical result sets

A Notes result-set link stored in an old chat message must reopen the **historical result set that was
found at that time**, not silently recompute against current knowledge.

The restored Notes state should include:

- the query text used then;
- the structured filters used then;
- the ordered/listed note identities returned then;
- a clear indication that these are historical/stale results rather than a current live search.

The user can explicitly press the intelligent-search action again to rerun the same query/filter state
against current Odyssey knowledge and obtain refreshed results.

Conceptually:

```text
old chat result link
      |
      v
Notes: historical result snapshot
query + filters + old note set
"These results may be out of date"
      |
      `-- press intelligent search --> recompute current results
```

The durable representation is the bounded stable-ID snapshot specified under
[Historical Chat -> Notes snapshots](#historical-chat---notes-snapshots). Do not duplicate full note
contents into chat/history merely to preserve a result set.

## Surface-state preservation

Chat and Notes are persistent product surfaces rather than reset-on-navigation pages.

Minimum expected behavior:

```text
Chat: scroll + draft
        |
        v
Notes: query + filters + sort + current note + note-nav history
        |
        v
Chat resumes exactly where left
        |
        v
Notes resumes exactly where left
```

Ordinary top-level switching preserves this state for the active page lifetime. Reload/reopen restores
the already-durable Chat transcript but starts Notes at its default feed; UI-2 does not add durable
Notes-view state or browser storage.

## Progressive learning direction (deferred from UI-2)

Odyssey may later teach advanced usage progressively with occasional contextual tips rather than an
up-front tutorial or permanent banner. A small lightbulb-style hint can appear when the surrounding
interaction makes the capability relevant, for example explaining property filters after repeated
structured searches.

Tips should become more advanced as the user encounters more advanced capabilities, but they should
remain sparse and dismissible. Do not implement this onboarding system as part of UI-2 unless a later
explicit contract pulls it into scope.

## Acceptance criteria for the later implementation phase

Before UI-2 is considered complete, deterministic and isolated-DEV evidence should demonstrate at
least:

1. persistent top-level Chat/Notes selector with state preservation across switching and the bottom
   edge left available for surface-specific interaction;
2. paginated/incremental Notes feed without whole-vault rendering;
3. deterministic default relevance ordering plus chronological sort alternatives;
4. immediate zero-provider text search while typing;
5. explicit intelligent search producing ranked notes, not a prose answer;
6. schema-driven general/type-specific filters with visible independent filter chips;
7. human-readable note detail with bounded properties, tags, dates, body, and clickable internal links;
8. backward/forward note navigation;
9. explicit backlinks with context and a reliable recency ordering;
10. chat result-set links that open Notes rather than synthesizing every result;
11. historical result-set restoration with stale indication and explicit rerun against current knowledge;
12. no raw frontmatter exposure, hidden reasoning, prompt/provider payload, or second note authority;
13. generation-bound cursors that fail closed rather than mix pages across an index change;
14. bounded historical snapshots containing stable IDs/metadata but no copied note bodies;
15. schema-derived filter controls that expose no unsupported browser-only operator;
16. inherited planner prompt plus deterministic and focused live evidence for result-presentation intent;
17. mobile human validation for visual density, smooth scrolling, filters, links, and navigation state.

## Out of scope

UI-2 does not include:

- note editing or creation from the Notes surface;
- semantic `related notes` recommendations;
- multiple open-note tabs on mobile;
- Calendar/Tasks/Events implementation;
- app marketplace/general plugin UI;
- proactive onboarding/tip engine;
- a new note database or duplicate canonical store;
- automatic provider calls for each typed character;
- automatic navigation from Chat to Notes for every list-shaped request.

## Architecture challenge result — 2026-09-19

Result: **PROCEED**.

The actual problem is to expose bounded read projections over the existing canonical notes while
preserving stable identity, current Markdown grounding, and one search/planning authority. The
smallest architecture extends the existing Core retrieval index and runtime boundary; it does not add
a notes database, graph service, browser-side knowledge index, second planner, or new application
server.

```text
canonical validated Markdown
          |
          v
Core Notes query service
  +-- extended rebuildable ContextIndex
  +-- schema-derived filters/capabilities
  +-- current-note re-grounding
          |
          v
thin runtime Notes operations
          |
          v
n8n identity + same-origin route projection
          |
          v
Notes UI presentation + in-session interaction state
```

This keeps the existing ownership split intact: Core decides note/query/link semantics; the runtime
only adapts typed operations; n8n authenticates, validates, and routes; the browser owns rendering and
ephemeral interaction state. Canonical Markdown remains the only knowledge authority.

### Core and runtime contract

Add one reusable Core Notes query boundary with four typed outputs rather than UI-specific filesystem
access:

- `NoteCapabilities` projects canonical type IDs/names and filterable fields/operators from
  `config/note-schema.json` plus Core's existing `supported_filter_operators()` contract;
- `NotePage` returns bounded note summaries, canonical applied filters, ranking/sort version, and an
  optional next cursor for feed, local search, intelligent search, or an ordered historical snapshot;
- `NoteDetail` returns one currently validated note by stable ID, its human-facing metadata/body, and
  Core-resolved explicit link occurrences; vault paths remain internal;
- `BacklinkPage` returns bounded explicit incoming-link sources and mention context for one stable ID.

The query input reuses `ContextFilter` and supports `feed | local | intelligent | snapshot`, explicit
sort, a default page size of 20, and a hard maximum of 40. Snapshot mode accepts only the bounded,
already-validated stable-ID order stored with a chat turn. Every returned page/detail/backlink source
is reread and schema-validated against current Markdown before exposure. Missing, deleted, malformed,
identity-mismatched, or stale indexed material fails closed; the derived index never becomes read
authority.

Extend the existing rebuildable `ContextIndex` with the minimum presentation/search projection needed
for Notes: lifecycle fields, normalized lexical text, and explicit resolved link edges/occurrences.
Keep it in the existing runtime SQLite artifact and rebuild it from Markdown with the current atomic
replacement behavior. `SemanticEntityIndex` remains identity-candidate infrastructure and must not be
repurposed as the Notes knowledge search authority.

The runtime exposes these as narrow internal Notes operations. n8n adds one same-origin `/api/notes`
product route with an operation discriminator (`capabilities`, `query`, `intelligent`, `detail`, or
`backlinks`), applies the same trusted actor projection as conversation/request traffic, and forwards
to the private runtime. n8n does not rank, parse Markdown, resolve links, or call an answerer for Notes.

### Ranking and pagination

All ranking is versioned and deterministic. Stable ties use normalized canonical name and stable note
ID; a filesystem path is never a product tie-breaker.

The default feed captures one `as_of` timestamp on its first page and computes:

```text
own activity band (age is UTC-normalized and clamped to zero for a future timestamp):
  updated < 7 days       -> 4
  updated < 30 days      -> 3
  updated < 90 days      -> 2
  updated < 365 days     -> 1
  older                  -> 0

connected activity band = highest band of an explicit incoming/outgoing neighbor, else 0
degree bucket            = min(4, floor(log2(1 + unique explicit neighbor count)))
feed score               = 100 * own_band + 5 * connected_band + degree_bucket
```

Sort by feed score descending, then `updated_at` descending, `created_at` descending, normalized name,
and stable ID. A link signal therefore cannot cross even one own-activity band, and raw link count is
log-bounded. There is currently no reliable note-view/use event stream, so UI-2 does not manufacture
an interaction signal from chat text or diagnostics. `Recently updated`, `Recently created`, and
`Oldest created` use the relevant lifecycle timestamp plus the same stable ties.

Immediate local search uses a deterministic lexical tier, in this order:

1. exact normalized canonical name;
2. exact normalized alias;
3. canonical-name or alias prefix;
4. every query token present across name/aliases/tags/filterable property text;
5. every query token present in canonical body text.

Within a tier, use the capped matching-token/occurrence count, then `updated_at`, normalized name, and
stable ID. This projection is local and rebuildable; typing never invokes embeddings or a provider.

Intelligent search applies schema filters as hard restrictions, promotes exact canonical-name then
exact-alias matches, and otherwise orders by the existing `ContextIndex` whole-note cosine similarity
for that one query. Local lexical tier, `updated_at`, normalized name, and stable ID are deterministic
ties. Cosine similarity is comparable only within the same query/index/model generation: it is rank
evidence, never identity confidence, an absolute product score, or mutation authority. Existing exact
name/alias normalization is legitimate reusable evidence; the identity index's semantic score and
historical benchmark-only fact fusion are not reused for Notes ranking.

Each first page fixes `as_of`, an index-generation digest (schema/ranking version plus sorted active
stable IDs/source hashes), and a normalized query/filter/sort fingerprint. The opaque cursor carries
those values and an offset. Later pages perform no provider call and are accepted only for the exact
same fingerprint and generation; a changed index returns `STALE_CURSOR` so the UI can explicitly
refresh instead of mixing two vault states.

### Explicit intelligent search and Chat result sets

The explicit Notes intelligent-search action invokes the existing Luna-first request planner once
(including only its already-bounded fail-closed fallback behavior). It reuses the same dynamic schema
capabilities and validated `SelectionCriteria`; there is no Notes-specific natural-language planner.
UI-2 accepts one direct `RetrieveAction`, combines its validated type/filters with the user's already
visible explicit filters, and sends the resulting semantic query to `ContextIndex`. A clarification,
write, delegation, multiple independent retrieval branches, or currently unimplemented `link_scope`
returns a bounded non-executing status rather than silently dropping meaning. The response contains
ranked note summaries and visible canonical filter chips, never generated prose, and never invokes the
grounded answerer.

To distinguish Chat enumeration from synthesis without keyword routing in n8n, extend the existing
top-level validated planner result with one bounded presentation intent:

```text
answer | note_set | answer_and_note_set
```

`note_set` and `answer_and_note_set` require retrieval evidence. The former bypasses the answerer and
returns a compact Notes affordance; the latter preserves the grounded Chat answer and adds the same
affordance. Both obtain the bounded ordered note set through the same Notes query service rather than
hydrating/synthesizing every match through the normal answer-context limit. This is an extension of the
one existing planner authority, not another classifier. Because
it changes a production model-facing contract, implementation must inherit the current validated
planner prompt and pass deterministic schema/fail-closed tests plus focused live planner evidence and
regression sentinels before adoption.

### Historical Chat -> Notes snapshots

Reuse the assistant turn in the root-bound durable main conversation. Add one optional versioned
`note_result_snapshot` beside (not inside) the diagnostic `request_detail`; do not create a snapshot
database or copy note bodies. The existing request ID/role idempotency covers the snapshot with the
turn. Version 1 contains only:

- query text (maximum 512 UTF-8 bytes);
- at most 16 canonical type/property filters;
- sort/ranking version and execution timestamp;
- at most 64 unique stable note IDs in returned order;
- total matched count and an explicit `truncated` flag.

The snapshot has its own 16 KiB encoded limit, while the diagnostic request-detail limit remains
unchanged. A chat result set is therefore explicitly a bounded historical prefix when more than 64
notes matched; the affordance must say so rather than imply completeness. Reopening preserves
membership/order but rehydrates current titles/types from canonical Markdown. Missing or now-deleted
IDs remain visible as unavailable historical members; they are never replaced silently. The surface
is labeled historical/stale because membership reflects the old execution while displayed note
content is current. Explicit rerun uses the saved query/filters against current knowledge and creates
a new result, leaving the old turn unchanged.

Snapshot metadata never enters the planner's recent conversation context: the existing UI-0 boundary
continues to forward only visible role/text turns.

### Backlinks and chronology

Derive backlinks only from literal canonical wikilinks. One Core parser extracts safe targets,
occurrence counts, and bounded source context. The index resolves a full vault-relative target against
the validated path-to-stable-ID map, or a basename target only when it identifies exactly one active
note; ambiguous, unresolved, or unsafe links never become backlink authority. Store only derived edges
and occurrence evidence in `ContextIndex`; current Markdown remains authoritative.

Order backlink source notes by their canonical `updated_at` descending, then normalized source name
and stable ID. This is reliable Odyssey-owned source-note activity, not a claim about when an
individual link was first written. Do not use `happened_at`, capture-heading dates, filesystem mtime,
or inferred mention time. Existing Git history was examined but is not the initial ordering source:
it has no current per-link chronology contract and is not guaranteed for every note. Adding `git blame`
or history parsing solely for backlink order would be a new fragile mechanism. UI wording should
therefore say recently updated sources, not recently linked facts.

### Schema-driven filters

The runtime capability projection is the only UI registry for property availability and operators.
Controls map the existing Core-supported kinds as follows:

| Schema capability | UI control |
| --- | --- |
| controlled `string` (`eq` / `in`) | single/multi select |
| ordinary `string` (`eq` / `in`) | exact text value/list |
| `array[string]` (`contains`) | chip/multi-value selector |
| `date` | exact date or bounded date range |
| date-time formatted `string` | timezone-aware date/time range |
| `integer` | exact value or bounded numeric range |

Type-specific controls appear only after the selected type makes their `applies_to` set valid. Tags
and aliases use their actual array-membership contract; the UI does not invent fuzzy filter semantics.
Boolean, free-form float/number, enum, or reference controls are not exposed because the current Core
filter contract does not support those property kinds. If a future canonical schema introduces one,
Core's shared filter validator/operator projection must support it before the UI can render it.

### Type presentation ownership

Keep type icon/color metadata in a small browser presentation map keyed only by canonical type ID.
Type names, meanings, properties, and filter behavior continue to come from the schema capability
projection. The map contains bundled SVG token plus restrained CSS color token and has one neutral
fallback for an unknown future type. It is not a duplicate semantic type registry. UI-2 makes no
change to `config/note-schema.json`.

### Notes state and frontend structure

Notes state is one in-memory controller for the current page lifetime: query text, explicit/inferred
filter chips, sort, loaded pages/cursors, feed scroll, current note, backward/forward note stack, and
historical-snapshot marker. Switching with the top-level selector hides rather than destroys each
surface, preserving both Chat's scroll/draft and this Notes state. A reload restores the already-durable
UI-0 transcript but starts Notes at its default feed. UI-2 adds no local/session storage and no durable
Notes-view state. Historical result links remain reload-safe because their snapshot belongs to the
durable chat turn, not the transient Notes controller.

Keep the dependency-free frontend and split only at the new responsibility boundary:

- `app.js` becomes shell/bootstrap/top-level surface navigation;
- `chat.js` owns the current Chat DOM, pagination, composer, retry, and request-detail behavior;
- existing `client.js` remains the bounded Chat transport/validation module;
- `notes-client.js` owns `/api/notes` transport and strict response validation;
- `notes.js` owns Notes state, navigation, and DOM rendering;
- a small Notes presentation module owns type tokens and safe Markdown/link rendering when that
  responsibility no longer fits clearly in `notes.js`.

Use DOM APIs rather than `innerHTML`; Core supplies stable link identities/occurrences so browser code
does not reimplement note identity resolution. Do not add a framework, bundler, generic component
system, or application/plugin registry for UI-2.

### Reuse and non-blocking implementation detail

UI-2 deliberately reuses `VaultRepository`, note parsing/validation, `ContextFilter`, schema capability
projection, whole-note `ContextIndex` embeddings, exact name/alias normalization, runtime identity
mapping, the n8n product boundary, UI-0's bounded-cursor and durable-turn patterns, and the current
mobile bottom-sheet treatment for filters/detail where useful. It does not treat conversation text,
request diagnostics, Git commits, or derived SQLite rows as knowledge.

Exact SVG glyphs, restrained color values, snippet typography, and localized microcopy remain
non-blocking DEV visual details within this contract. No material product, source-of-truth, schema,
security, or infrastructure decision remains open before implementation.
