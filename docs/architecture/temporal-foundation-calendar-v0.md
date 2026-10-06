# Temporal Foundation + Calendar v0

## Current conversational ownership

The original Calendar-planner routing work below is retained as historical evidence, but the active chat architecture is simpler: Router sends ordinary dated knowledge to built-in Temporal, Temporal resolves every material date/time mention in source order, and Core performs semantic ownership, identity/reference resolution, clarification, and mutation planning. Calendar remains the presentation/query application over canonical day data. `calendar_day` is Core-owned and can be selected only for an authorized exact date (or the current local day for ordinary daily capture), preserving deterministic `date:YYYY-MM-DD` identity and `calendar/days/YYYY-MM-DD.md` paths. Multiple exact dates/date-times may be handed to Core together and every supplied temporal wording/value pair must be preserved by a durable write. Exact date-times are represented by one shared `TemporalAnchor` (date plus optional exact local time/offset), so Core can preserve `HH:MM` presentation without turning hours into Notes or Calendar entities. At the model-facing Temporal boundary, an unambiguous local wall time may be deterministically localized with the supplied IANA timezone; canonical Core anchors remain offset-aware, while ambiguous or nonexistent DST wall times fail closed. Date ranges remain normalized Temporal results but intentionally stop before generic Core planning until a safe canonical write representation is approved.


Status: **active deterministic architecture uses Router -> built-in Temporal -> Core for dated chat knowledge. Calendar is read/presentation only. Earlier Calendar-planner live gates remain historical evidence and do not authorize the current boundary.**

## Objective

Introduce the smallest shared temporal foundation and first Calendar capability needed before Tasks, so Odyssey can treat dates as navigable, linkable context without making every dated statement an event, task, reminder, or ordinary semantic Note target.

The user should be able to open any calendar day, see what belongs to that day, write literal day-owned knowledge when appropriate, and navigate temporal links while canonical Markdown, identity, backlinks, Git history, and Core safety remain one shared authority.

This phase deliberately precedes Tasks because Tasks will later project `due_date` onto the same temporal surface instead of inventing its own date semantics.

## Approved architecture

A calendar day is a **Core-owned deterministic canonical destination**, not an ordinary unrestricted semantic Note type.

It reuses the canonical Note substrate:

- human-readable Markdown;
- schema validation and stable identity;
- normal links/backlinks;
- Git/request history;
- the existing renderer/editor infrastructure where useful;
- the same local-first vault authority.

Core owns deterministic Day identity/materialization. The generic planner may use `calendar_day` only when runtime has authorized the exact date (or today for ordinary day capture); it cannot search or create arbitrary Day targets like `person`, `project`, `document`, or a later `task`. Calendar owns only deterministic projection/presentation.

Conceptually the type boundary is:

```text
canonical Note types
  ├── ordinary semantic types
  │     ├── person
  │     ├── project
  │     ├── document
  │     └── journal_entry (legacy read compatibility; not a new write destination)
  └── Core-managed deterministic destinations
        └── calendar_day
```

The exact schema metadata used to express deterministic/managed planner visibility or default Notes-feed visibility is an implementation detail to keep minimal and validated. Do not introduce a generic plugin/package framework merely to express this one boundary.

## Temporal identity and materialization

Every valid calendar date has a deterministic logical identity, conceptually:

```text
date:YYYY-MM-DD
```

That identity exists even when no Markdown file exists. Calendar resolves a date directly; it never performs semantic entity search to find “tomorrow's note”. The current Core implementation uses this same `date:YYYY-MM-DD` value as the stable canonical Note `id` after materialization, so virtual and materialized representations do not undergo an identity transition.

A day is virtual by default and materializes as canonical Markdown only when:

1. the user/application writes content owned by that day; or
2. canonical Markdown contains an explicit link whose target is that day.

A structured temporal property alone does **not** materialize the day. Future examples include task/event temporal properties; legacy `journal_entry.entry_date` remains projectable for historical entries without authorizing new Journal writes.

A materialized day uses a deterministic Core-owned temporal path such as:

```text
calendar/days/2026-10-01.md
```

The logical temporal identity and physical Markdown target are distinct. A normal Obsidian wikilink can therefore target the deterministic Calendar path while Core/Calendar maps it to the temporal identity, for example conceptually:

```markdown
[[calendar/days/2026-10-01|01-10-2026]]
```

Do not introduce a second incompatible backlink protocol when ordinary wikilinks can preserve the same authority and navigation behavior.

## Temporal Foundation boundary

Core owns only reusable temporal primitives needed by multiple capabilities:

- strict dates and date-times;
- timezone-aware current context;
- deterministic day/week/month/year ranges;
- validation/comparison of normalized temporal values;
- a shared `TemporalAnchor` coordinate (`date` plus optional exact `time`/UTC offset) for durable fact semantics;
- deterministic Calendar-day identity/reference handling.

Core does **not** become a calendar application, event model, or reminder scheduler. The built-in Temporal interpreter performs only bounded natural-language date/time normalization using current date/time/timezone context; Core consumes that trusted evidence and must fail closed when chronology cannot be established safely. `EXACT_DATE` and `EXACT_DATETIME` may reach ordinary Core knowledge planning. `DATE_RANGE` and unresolved temporal wording remain fail-closed until an explicitly approved generic representation exists.

## Routing and knowledge ownership

Natural-language routing is owned by the cross-cutting [Application Boundary + Router v0](application-boundary-router-v0.md). Calendar is not a chat destination. Router first partitions the current message only where exact source spans are independently interpretable; independent dated intentions may therefore become separate Temporal routes, while clauses with shared temporal scope, predicates, or ellipsis remain together. For otherwise ordinary Core-owned knowledge whose date/time wording matters, Router selects built-in Temporal; Temporal returns only normalized temporal evidence plus the unchanged routed source text; Core then decides semantic ownership and the write shape.

Examples:

```text
"El fontanero viene mañana"
    -> Router -> Temporal resolves tomorrow -> Core decides the authorized Day-owned write

"Marta empezó hoy en Airbus"
    -> Router -> Temporal resolves today -> Core writes Marta-owned durable knowledge with temporal evidence

"Escribe en mi diario que hoy..."
    -> Router -> Temporal/Core -> today's calendar_day content; no separate Journal object

"Tengo que llamar al banco el viernes"
    -> Tasks owns the task semantics and may consume Temporal for the due date
```

`calendar_day` does not need to appear among ordinary unrestricted Core-planner-selectable note types. Runtime exposes only the exact trusted dates Core may choose for the current request. Calendar later projects the resulting canonical day data; it does not interpret the chat request or plan the mutation.

Specialized application planners remain domain-local and may depend on Temporal, but Core remains the canonical mutation authority.

## Literal day capture versus identity resolution

A Calendar Day may contain literal human-readable facts without forcing every noun phrase or relational phrase to resolve to canonical identities.

The governing rule is:

```text
Can the user's requested outcome be fulfilled completely
while preserving an unresolved expression literally?

YES -> literal day capture is allowed.
NO  -> the required identity/set must resolve; otherwise clarify.
```

Examples:

- `Mañana vienen mis amigos` may be preserved literally when the request is only to remember that occurrence.
- `Añade a mis amigos como asistentes` requires the intended people to resolve; failure must clarify rather than silently save an unresolved literal substitute.
- `Hoy vino el fontanero` does not by itself authorize creation of a `person` note named `El fontanero`.

Core must never turn failed identity resolution into literal Calendar capture on its own. The validated plan/capability intent must authorize the literal capture path.

Writing directly inside an opened Day means literal Day content by default. It does not silently create a Task/Event merely because the text sounds actionable or scheduled; explicit intent or later specialized routing owns those application objects.


## Journal convergence follow-up

Everyday diary capture now converges on the canonical Day instead of creating a second date-bound
knowledge object. Wording such as `mi diario` does not create a separate Journal or require Calendar
to participate in chat. Temporal resolves any material date wording (with the current local Day as the
ordinary default) and Core decides whether the knowledge is Day-owned, then performs canonical Day
persistence and shared safety.

`journal_entry` remains in the canonical schema only for historical read/filter compatibility. It is
not exposed in planner write capabilities, so new typed Journal creation/amendment is rejected. No
existing Journal Markdown is migrated or deleted by this follow-up. Calendar may continue projecting
legacy entries by `entry_date` until a later explicitly approved migration removes the legacy type.

## Three temporal relationships must remain distinct

Calendar may present several kinds of relationship to the same day, but they are not one canonical mechanism:

1. **Semantic/application time** — structured values such as later Task/Event dates/times and legacy `journal_entry.entry_date`. Calendar projects these deterministically without adding duplicate wikilinks.
2. **Explicit temporal reference** — a canonical fact/body contains an intentional wikilink to the Day. This is a real Markdown backlink.
3. **Odyssey activity/provenance** — notes/facts/tasks/events created, corrected, removed, or completed on that date. Atomic facts retain their exact capture timestamp as Odyssey-owned hidden marker metadata (`recorded_at`), while the human-visible Markdown remains uncluttered. Request/Git/application history remains the broader provenance authority and should not be duplicated as visible prose merely to appear on Calendar.

Technical/internal changes that do not represent useful user-visible semantic activity should not clutter the Day activity surface.

## Capture chronology

The existing invariant remains:

```text
captured_at != happened_at
```

If knowledge belongs semantically to another date, the fact keeps that date/reference while request/Git history still records when Odyssey captured it.

The already-approved formatting follow-up for atomic facts remains required: when a Note already has an Odyssey `# Added DD-MM-YYYY` section for the current capture date, later facts captured on the same date group under that one heading rather than adding another identical heading.

The rendered capture date should become navigable to the corresponding Calendar Day without weakening existing fact markers, request provenance, correction/removal authority, or tolerance for historical duplicate same-date headings.

Implementation note after the temporal-anchor follow-up: current Odyssey-created capture headings render only the capture **day** as an ordinary wikilink to `calendar/days/YYYY-MM-DD`, while every new atomic fact stores its exact offset-aware `recorded_at` in the hidden Odyssey marker. The same marker may also carry one or more canonical semantic `temporal` anchors. These values are deliberately separate: `recorded_at` means when Odyssey persisted the fact; `temporal` means when the fact says something happened/will happen. Legacy markers without either field remain readable and no historical time is invented. Exact semantic date-time facts owned by another entity render a canonical Day link followed by the local clock (`[[...|DD-MM-YYYY]] 15:35` when seconds are zero); a fact owned by that same Day renders only `15:35` and retains the exact date-time in hidden metadata, avoiding a self-link. Later same-day captures still append beneath the last matching capture section instead of creating another heading. A provider-free Core end-to-end test covers write -> Markdown -> Day materialization -> context-index rebuild -> detail link resolution -> incoming backlink projection, and focused tests cover hidden capture/semantic-time separation.

## Calendar v0 product surface

Calendar justifies a dedicated visual surface because temporal navigation is not well represented by the ordinary Notes feed.

The first version contains:

- a month view;
- a Day view opened by selecting any date;
- transparent handling of virtual versus materialized days;
- Day-owned literal content;
- explicit incoming temporal links/backlinks;
- legacy Journal/date associations plus supported Task/Event temporal projections as they exist;
- useful semantic activity for that date.

Core-managed Day notes do not appear in the ordinary Notes feed by default, although the same underlying Markdown may reuse existing reading/editing infrastructure.

Week uses Monday through Sunday in v0. Locale/user-configurable week starts are deferred. Week/month/year are calculated views over date ranges, not separately persisted Notes in this phase.

The original v0 decision deferred a scheduling-style hourly week/day/three-day grid until real timed
objects justified it. That condition is now partially met: Tasks owns structured planned start/end
coordinates and Core atomic facts can carry exact semantic `TemporalAnchor` times. The later
[Calendar multi-day schedule view](calendar-multiday-schedule-view.md) therefore adds a read-only
1/3/7-day hourly projection over those existing canonical coordinates without inventing hours or
creating Event semantics inside Calendar. `recorded_at` remains capture chronology, never semantic
schedule position. Events still owns future occurrence lifecycle/recurrence and will project into the
same schedule surface rather than requiring a second calendar model.

Implementation note after Slice 4: Calendar now owns its deterministic `month` + `day` projection and presentation boundary under `odyssey_apps/calendar/`, while reusable temporal/Day primitives remain in Core. It also has a dedicated framework-free browser surface. Month projection scans current validated canonical Markdown and exposes bounded indicators for Day-owned content, Journal `entry_date`, same-day captured facts, and explicit temporal references; Day projection keeps those categories separate and opens virtual dates without materialization. Browser responses contain only Core-resolved presentation blocks and stable Note summaries, never raw vault paths or browser-side Markdown parsing authority. Notes date links hand navigation to Calendar, while Calendar related-note controls hand navigation back to Notes. Provider-free backend and browser end-to-end tests cover real canonical write -> Day chronology/materialization -> index rebuild -> month/Day projection and month -> Day -> related Note navigation. The checked-in DEV route inventory includes the Calendar modules/API, but no live DEV or public-route deployment is implied by the implementation commit.

Implementation note after DEV validation: journal entries are projected only onto their semantic `entry_date`; their capture chronology remains available to Odyssey history but no longer duplicates them under another Day's `Captured` section. Day navigation deduplicates identical in-flight requests and gives only the newest navigation request authority to update the visible state, preventing rapid taps from building duplicate work or letting stale responses/errors replace a newer Day. Deterministic regression tests preserve both failure boundaries.

### Deferred temporal index optimization

Calendar v0 intentionally keeps its current Markdown scan while scale remains small and measured query cost is low. The first DEV slowdown investigated during rapid Day navigation was caused by duplicate concurrent browser requests and queueing, not by Core's Markdown scan; the UI concurrency fix therefore remains the correct immediate remedy.

When measurements show vault-size scan cost becoming material, optimize by extending the existing rebuildable `context.sqlite3` index rather than introducing `calendar.sqlite3` or another authority. The intended query shape is:

```text
Calendar date/month query
        -> context.sqlite3 selects relevant stable note IDs
        -> Core hydrates only those canonical Markdown Notes
        -> Calendar renders the same projection contract
```

Reuse indexed schema properties for temporal fields such as `journal_entry.entry_date` and later `task.due_date`, and reuse indexed note links for explicit Day backlinks. If capture chronology becomes a measured bottleneck, add the smallest rebuildable Core-owned projection needed to index `Added` dates/fact locators, with SQL indexes suited to date/range lookup. Markdown remains authoritative; every SQLite temporal projection must be disposable and reconstructible from canonical Markdown. Incremental index maintenance is a separate later optimization and should be justified by rebuild measurements rather than bundled speculatively with Calendar.

## Application sequence and composition

The approved near-term order is now:

```text
Temporal Foundation
        ↓
Calendar v0
        ↓
Tasks
        ↓
Events
        ↓
Reminders
        ↓
bounded maintainability checkpoint
        ↓
Projects / later applications
```

This does not make Calendar the owner of Tasks, Events, Journal, or Reminders. Each capability owns its lifecycle/state and exposes only the temporal values Calendar needs to project it.

Applications may depend on lower-level capabilities when useful and must keep those dependencies explicit and non-circular. Calendar/temporal semantics are lower-level shared behavior; Tasks and Events must not independently reimplement date navigation or Day identity.

## Acceptance criteria

1. Any valid ISO date can be addressed as one deterministic Calendar Day without semantic entity search, even when no Markdown file exists.
2. `calendar_day` uses the canonical Markdown/validation/history substrate but cannot be selected or created as an ordinary semantic Note type by the generic planner.
3. A virtual Day materializes only for Day-owned content or an explicit canonical link to that Day; a temporal property alone does not create a file.
4. Reopening/materializing the same date is idempotent and never creates duplicate Day identities/files.
5. A Day can store independent literal atomic facts with normal provenance and targeted correction/removal behavior.
6. Identity-dependent operations never degrade silently into literal Day text when required identity/set resolution fails.
7. Ordinary entity-owned knowledge remains stored once on its natural owner; an explicit temporal reference makes it discoverable from the corresponding Day without duplicating prose.
8. New everyday diary/journal capture is Day-owned `calendar_day` content; historical `journal_entry` notes remain valid/readable and project to their `entry_date` Day until an explicitly approved migration retires them.
9. Same-day atomic captures in one ordinary Note group under one current-date `Added` heading, while historical duplicate headings remain valid input.
10. Capture dates and explicit temporal references are navigable to the correct Day using ordinary validated link/backlink machinery.
11. Calendar v0 month + Day views expose Day content, temporal projections, explicit references, and useful semantic activity while excluding application-managed Days from the ordinary Notes feed by default.
12. Existing ordinary Note READ/WRITE, identity resolution, backlinks, filtering, planner type capabilities, and current Journal behavior remain regression-safe.

## Out of scope

- Tasks, task status/subtasks, Projects, Events, recurrence, Reminders, notifications, attendees, invitations, or external calendar sync.
- Pre-materializing Days for every date or for every structured temporal property.
- Persisted week/month/year Notes or user-authored period pages.
- Hourly week/day scheduling UI before Events exists.
- A general plugin marketplace/package system or broad application manifest framework.
- A new graph database, calendar database, event service, or second canonical knowledge store.
- A comprehensive custom natural-language date parser when the existing planner + deterministic date validation suffices.
- Automatic entity creation from unresolved literal Day text.
- Destructive migration, deletion, or rewriting of historical `journal_entry` notes; legacy data remains readable until separately approved.
- Technical/internal activity noise presented as personal calendar activity.
- Production deployment as part of this phase's initial implementation work.

## Proposed implementation slices

1. **Managed canonical type boundary.** Add the smallest schema/Core capability that lets one canonical Note type be Calendar-managed, hidden from ordinary planner type selection and default Notes feed behavior while retaining normal validation/storage guarantees.
2. **Temporal/Day Core primitives.** Deterministic date identity, virtual/materialized Day repository behavior, collision/idempotence checks, and strict date/range helpers.
3. **Temporal links and chronology.** Explicit Day links/backlinks plus the approved same-day `Added` heading grouping/navigation, keeping capture time separate from described/event time.
4. **Calendar v0 read/UI surface.** Month + Day projections over virtual/materialized Days, Journal temporal properties, explicit links, and useful semantic activity.
5. **Temporal-routed natural language.** Route ordinary dated/timed Core knowledge through built-in Temporal without giving Calendar a chat planner; `EXACT_DATE` and `EXACT_DATETIME` become shared Core temporal anchors, while range semantics remain fail-closed. Specialized applications such as Tasks may depend on the same Temporal contract.

Implementation note after Slice 5 deterministic work: Calendar's separate GPT-6 Luna planner (current Slice 6 candidate effort: `low`)
contract retains `EXACT_DATE`, `DATE_RANGE`, and `UNSPECIFIED` temporal evidence. Exact Day literal
captures use the exact routed source wording and a Core-owned capture primitive; ranges and vague
time never become an invented Day, and unsupported Tasks-like lifecycle intent fails closed. Range
resolution is therefore preserved now, but a natural-language range-aware read/write operation is
not yet enabled in this slice. An entity-owned exact-date statement may use the opt-in shared Core
temporal-reference compiler part, so Core still resolves identity and renders/persists the canonical
Day link. The default Core planner contract is hash-pinned unchanged. The frozen provider-free
regression matrix was consumed unchanged by Slice 6 Attempt 1. That gate retained 11/16 passes and
failed overall; no live adoption occurred. The same frozen matrix now guards a general prompt revision
whose successor live attempt still requires separate authorization.

Each slice must prefer existing Note/storage/link/history primitives over parallel Calendar implementations.

## Open decisions

Calendar's product semantics remain settled. Cross-cutting routing/application-boundary decisions are now owned by [Application Boundary + Router v0](application-boundary-router-v0.md) and must be resolved there before Slice 5 implementation. Exact schema flag names, internal class/function names, URL/API shapes, and presentation details remain implementation choices so long as they preserve these contracts.

## Architecture challenge

Result: **PROCEED after approved reconsideration**.

The first hybrid proposal treated Calendar Days as Markdown resources outside the canonical Note type system. Review found that this would duplicate or special-case validation, links/backlinks, editing, history, and future direct-Markdown ingestion.

The approved simpler boundary keeps one canonical Markdown/Note substrate and distinguishes ordinary semantic types from the Core-managed deterministic `calendar_day` destination. The planner cannot search/create arbitrary Day entities; it may target only runtime-authorized dates, while Calendar reuses the resulting canonical state for presentation and navigation.

The human explicitly approved this reconsidered boundary and the application principle that a selected app/capability may resolve its own bounded functionality deterministically or with a separately justified AI boundary. No additional product decision is required before implementation.
