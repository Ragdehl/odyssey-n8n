# UI-2 — read-only Notes product contract

Status: **product behavior defined; architecture challenge and implementation not started**.

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

Use a persistent bottom navigation bar for the current two primary Odyssey surfaces:

```text
+-----------------------------+
|                             |
|          content            |
|                             |
+-----------------------------+
|      Chat        Notes      |
+-----------------------------+
```

The bottom bar is reserved for **major product surfaces**, not one tab per application. Future
capabilities such as Calendar may earn a primary destination if real use justifies it; secondary
applications can use another navigation mechanism later. Do not design that future app navigation in
UI-2.

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
the top forever merely because it has many old connections. Exact weights are an architecture/testing
decision, not a hidden model judgment.

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
presentation metadata should not be silently added to `config/note-schema.json`. During the
architecture challenge decide explicitly whether icon/color presentation belongs in a small UI
presentation map or whether there is a justified reason for optional schema presentation metadata.
A schema change is not authorized by this product contract alone.

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
where semantically appropriate, but the architecture challenge must verify what scores are comparable
and safe to expose/use for ordering rather than assuming every internal score is a product ranking.

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
- number -> bounded range;
- enum/list -> select/multi-select;
- boolean -> yes/no/any;
- link/reference -> note selector;
- tags -> chips/multi-select;
- text -> textual predicate/search appropriate to the existing property contract.

The note schema is the semantic source for what properties exist. The UI must not maintain an
independent hand-written copy of type properties.

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

The desired product order is **most recently active/referenced first**. The architecture challenge
must identify the correct reliable chronology for that ordering. Do not confuse `happened_at` with
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

The architecture challenge must choose the smallest safe durable representation. Do not duplicate
full note contents into chat/history merely to preserve a result set; stable note identities plus
query/filter/result metadata are the likely direction, subject to compatibility/privacy validation.

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

Normal reload/reopen semantics beyond already-durable state should be decided by the architecture
challenge based on what is useful and safe; UI-2 must at least preserve state across ordinary tab
switches in the active product session.

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

1. Chat/Notes bottom navigation with state preservation across switching;
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
13. mobile human validation for visual density, smooth scrolling, filters, links, and navigation state.

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

## Open architecture decisions

Product behavior above is defined. Before implementation, the architecture challenge must still decide
without changing the user contract silently:

1. exact reusable Core/runtime endpoint/query contract for note feed/search/filter/detail/backlinks;
2. exact deterministic ranking signals/weights and pagination/cursor contract;
3. which existing lexical/semantic retrieval scores can safely rank UI results;
4. how intelligent search returns both semantic query evidence and structured filters without adding a
   parallel planner/search authority;
5. smallest durable representation and size limits for historical result snapshots;
6. reliable chronology source for backlink ordering;
7. exact supported property-control mapping for current note-schema property kinds;
8. visual type presentation ownership: separate UI presentation map versus an explicitly approved
   optional schema presentation extension;
9. exact in-session versus reload persistence boundary for Notes UI state;
10. frontend modularization needed to keep `app.js`/`client.js` maintainable as Notes is added.

Any ambiguity discovered during this challenge should return to the human as an open decision rather
than being inferred from implementation convenience.
