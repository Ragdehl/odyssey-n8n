# Calendar rich month view

Status: **implemented and deterministically validated on the current feature branch; isolated-DEV
human visual review is next.** The approved architecture challenge returned **PROCEED**. This phase
does not authorize production promotion.

This phase replaces Calendar v0's dot-only monthly activity indicators with a compact, information-bearing
month surface inspired by the dense mobile month widget already validated by the user. It does not
change Calendar's temporal ownership, Day identity, Tasks semantics, canonical Markdown, or the
Router/Temporal/Core chat path.

## Objective

A user looking at the month should understand what is happening on a date without opening every Day.
Each date remains one Calendar navigation target, but its cell can show a bounded preview of the
canonical information already projected onto that date.

## Approved product behavior

The month keeps a Monday-to-Sunday seven-column grid. Compared with Calendar v0:

- date cells become taller and visually denser;
- on narrow screens the month grid may scroll horizontally so Day cells can remain meaningfully wider instead of forcing all seven columns into the viewport;
- the day number becomes a small, secondary label near the top;
- the current colored dots disappear;
- each date shows up to **four** compact preview rows;
- a preview row uses the same semantic Note-type icon/color presentation already shared by Notes, at a smaller month-view size;
- compact mode prioritizes the day-specific visible snippet and hides a redundant source Note name; the source label remains the fallback when no meaningful snippet exists (notably Task titles);
- an explicit expand/compact toggle widens the horizontally scrollable month substantially; expanded mode restores the source Note name and shows up to two visible lines of the day-specific snippet beneath it;
- the expand/compact choice is presentation-only session state and survives ordinary navigation/reload within the same browser session;
- when more preview entries exist, the cell shows a compact `+N` overflow indicator;
- selecting anywhere on the date cell still opens the existing Day view.

The first version does **not** claim to rank semantic importance. To avoid inventing another ranking
system, candidates follow Calendar's existing Day category order: Day-owned content, Journal,
captured information, Tasks, then explicit date references. Within a category, source ordering remains
the deterministic name/ID order already used by the Day projection. The month takes the first four
entries from that deterministic sequence.

One source/category contributes at most one preview row for a date. The preview total therefore means
the number of available preview entries, not the number of underlying atomic facts.

## Responsibility boundary

The browser must not issue a Day request for every visible date and must not parse Markdown. One
existing `month` request remains the authority for the whole grid.

Calendar's deterministic query layer may extend each monthly Day projection with a bounded list of
presentation-only preview entries derived from the same validated canonical state and Core-resolved
Note detail already used by the Day surface. A preview needs only:

```text
kind        day_content | journal | capture | task | reference
source_type canonical Note type used for semantic icon/color
label       short source/user-facing label
text        optional bounded visible snippet
```

The month response retains the existing materialized/content/category counts for compatibility and
accessibility. The browser only renders the new bounded preview projection; it gains no identity,
Markdown, ranking, mutation, or temporal semantics.

No LLM call, embedding search, new index, new service, or new persistence is justified by this phase.

## Acceptance criteria

1. A normal mobile month still fits seven columns without horizontal scrolling.
2. Each Day cell has room for up to four compact rows and a small day number.
3. Days with activity show semantic icons/colors and readable compact text instead of colored dots.
4. More than four preview entries produces `+N` without expanding the cell unboundedly.
5. The browser performs one month query, not one query per Day.
6. Calendar month preview data is grounded from current validated canonical Markdown through existing
   Core/Calendar read boundaries; raw Markdown never crosses into browser parsing.
7. Selecting the cell opens the same Day view and existing previous/next Day navigation still works.
8. Virtual empty Days remain openable and do not materialize knowledge.
9. Task completion from Day view and Notes navigation regressions remain covered.
10. Provider-free unit/contract and vertical browser/runtime tests cover preview selection,
    serialization/validation, overflow, rendering, and navigation.

## Out of scope

- hourly/three-day/week scheduling grids;
- drag/drop or direct mutation from the month grid;
- direct Note opening from an individual preview row in this first slice;
- Events lifecycle changes or new event semantics;
- user-configurable preview ranking/priority;
- per-user week-start settings;
- general localization work beyond the current Spanish presentation;
- changing Day-view category semantics.

## Open decisions

No material product decision blocks implementation. Exact cell height, typography, truncation length,
and the visual treatment of `+N` are presentation details to tune in isolated DEV. If real use later
shows that deterministic category order hides the information users care about, ranking can be
revisited with concrete evidence rather than introduced speculatively here.

## Implementation record

The existing Calendar month query now carries `preview_total` and at most four `previews` per Day.
Each preview is derived through Calendar's validated canonical scan and existing Core Note-detail
read boundary; it contains only the declared kind, canonical source type, an 80-character bounded
label, and an optional 120-character visible snippet. The existing
materialization/content/category counts remain unchanged. Candidates preserve the approved category
order (`day_content`, `journal`, `capture`, `task`, `reference`) and the existing case-folded
source-name/ID ordering within a category. Core Note detail is resolved only for the four preview
rows actually returned; overflow sources contribute only to the deterministic `preview_total`.

The browser validates the bounded projection, makes its existing one month request, and renders
compact Notes type badges plus the day-specific snippet (falling back to the source label only when
no snippet exists), with `+N` overflow inside the existing whole-cell Day navigation target. After
the first isolated-DEV mobile review, the month grid deliberately became horizontally scrollable on
narrow screens so columns can stay wider, and the semantic type badge was reduced further. A second
presentation-only toggle now offers an expanded reading mode: wider Day columns, source Note name,
and up to two snippet lines, while compact mode keeps the quicker scan-oriented presentation. The
choice is stored only in session storage. No preview row is independently navigable. The change
introduces no provider, prompt, model, workflow, persistence, index, or deployment change.
