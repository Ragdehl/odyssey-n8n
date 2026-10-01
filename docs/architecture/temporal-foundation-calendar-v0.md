# Temporal Foundation + Calendar v0

Status: **approved phase contract; implementation in progress (Slices 1-3 complete on the feature branch)**.

## Objective

Introduce the smallest shared temporal foundation and first Calendar capability needed before Tasks, so Odyssey can treat dates as navigable, linkable context without making every dated statement an event, task, reminder, or ordinary semantic Note target.

The user should be able to open any calendar day, see what belongs to that day, write literal day-owned knowledge when appropriate, and navigate temporal links while canonical Markdown, identity, backlinks, Git history, and Core safety remain one shared authority.

This phase deliberately precedes Tasks because Tasks will later project `due_date` onto the same temporal surface instead of inventing its own date semantics.

## Approved architecture

A calendar day is a **Calendar-managed canonical Note type**, not an ordinary planner-selectable semantic type.

It reuses the canonical Note substrate:

- human-readable Markdown;
- schema validation and stable identity;
- normal links/backlinks;
- Git/request history;
- the existing renderer/editor infrastructure where useful;
- the same local-first vault authority.

Calendar owns its deterministic lifecycle and routing. The generic planner must not treat `calendar_day` like `person`, `project`, `document`, or a later `task` when choosing an ordinary WRITE target.

Conceptually the type boundary is:

```text
canonical Note types
  ├── ordinary semantic types
  │     ├── person
  │     ├── project
  │     ├── document
  │     └── journal_entry
  └── application-managed types
        └── calendar_day
```

The exact schema metadata used to express `application-managed`, `Calendar-owned`, planner visibility, or default Notes-feed visibility is an implementation detail to keep minimal and validated. Do not introduce a generic plugin/package framework merely to express this one boundary.

## Temporal identity and materialization

Every valid calendar date has a deterministic logical identity, conceptually:

```text
date:YYYY-MM-DD
```

That identity exists even when no Markdown file exists. Calendar resolves a date directly; it never performs semantic entity search to find “tomorrow's note”. The current Core implementation uses this same `date:YYYY-MM-DD` value as the stable canonical Note `id` after materialization, so virtual and materialized representations do not undergo an identity transition.

A day is virtual by default and materializes as canonical Markdown only when:

1. the user/application writes content owned by that day; or
2. canonical Markdown contains an explicit link whose target is that day.

A structured temporal property alone does **not** materialize the day. Future examples include `task.due_date`, `event.start_date`, and the existing `journal_entry.entry_date`; Calendar can project those values onto a virtual day deterministically.

A materialized day should use a deterministic Calendar-owned path such as:

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
- deterministic Calendar-day identity/reference handling.

Core does **not** become a calendar application, event model, reminder scheduler, or comprehensive natural-language date parser. The planner may interpret natural temporal wording using its current date/time/timezone context; Core validates normalized results and must fail closed when chronology cannot be established safely.

## Routing and knowledge ownership

The generic planner continues to decide semantic ownership before mutation. Calendar is selected as a capability when the requested knowledge belongs naturally to a day rather than to an ordinary entity/application target.

Examples:

```text
"El fontanero viene mañana"
    -> Calendar day capture for tomorrow

"Marta empezó hoy en Airbus"
    -> ordinary WRITE owned by Marta, with an explicit temporal reference

"Escribe en mi diario que hoy..."
    -> Journal-owned knowledge with entry_date/day association

"Tengo que llamar al banco el viernes"
    -> later Tasks-owned knowledge with due_date/day association
```

Calendar routing does not require `calendar_day` to appear among ordinary planner-selectable note types. The planner preserves the specialized temporal-capture intent; Calendar resolves the normalized date deterministically and materializes/reuses exactly that day.

Applications may resolve their own bounded functionality deterministically or through a separately justified model boundary. Do not load every application's detailed contract into the top-level planner, and do not assume Calendar requires a second model call unless evidence shows deterministic routing plus the existing planner contract is insufficient.

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

## Three temporal relationships must remain distinct

Calendar may present several kinds of relationship to the same day, but they are not one canonical mechanism:

1. **Semantic/application time** — structured values such as `entry_date`, later `due_date`, or event start/end values. Calendar projects these deterministically without adding duplicate wikilinks.
2. **Explicit temporal reference** — a canonical fact/body contains an intentional wikilink to the Day. This is a real Markdown backlink.
3. **Odyssey activity/provenance** — notes/facts/tasks/events created, corrected, removed, or completed on that date. This is derived from existing request/Git/application history and must not be copied into every Note body merely to appear on Calendar.

Technical/internal changes that do not represent useful user-visible semantic activity should not clutter the Day activity surface.

## Capture chronology

The existing invariant remains:

```text
captured_at != happened_at
```

If knowledge belongs semantically to another date, the fact keeps that date/reference while request/Git history still records when Odyssey captured it.

The already-approved formatting follow-up for atomic facts remains required: when a Note already has an Odyssey `# Added DD-MM-YYYY` section for the current capture date, later facts captured on the same date group under that one heading rather than adding another identical heading.

The rendered capture date should become navigable to the corresponding Calendar Day without weakening existing fact markers, request provenance, correction/removal authority, or tolerance for historical duplicate same-date headings.

Implementation note after Slice 3: current Odyssey-created capture headings render the date as an ordinary wikilink to `calendar/days/YYYY-MM-DD`, materialize that Day before committing the source link, and append later same-day facts beneath the last matching capture section instead of creating another heading. Legacy plain-date headings and historical duplicate same-date sections remain readable/removable; a same-day append may upgrade only the selected current section to the navigable form. Explicit Day links introduced in other fact text use the same deterministic materialization/backlink path. A provider-free Core end-to-end test covers write -> Markdown -> Day materialization -> context-index rebuild -> detail link resolution -> incoming backlink projection.

## Calendar v0 product surface

Calendar justifies a dedicated visual surface because temporal navigation is not well represented by the ordinary Notes feed.

The first version contains:

- a month view;
- a Day view opened by selecting any date;
- transparent handling of virtual versus materialized days;
- Day-owned literal content;
- explicit incoming temporal links/backlinks;
- projected Journal/date associations and other supported temporal properties;
- useful semantic activity for that date.

Calendar-owned Day notes do not appear in the ordinary Notes feed by default, although the same underlying Markdown may reuse existing reading/editing infrastructure.

Week uses Monday through Sunday in v0. Locale/user-configurable week starts are deferred. Week/month/year are calculated views over date ranges, not separately persisted Notes in this phase.

Hourly week/day/three-day grids are deferred until Events provides timed objects that justify them. Calendar v0 must not create an empty Google-Calendar-style scheduling UI before the event contract exists.

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
8. Journal entries remain separate canonical objects and project to their `entry_date` Day.
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
- Technical/internal activity noise presented as personal calendar activity.
- Production deployment as part of this phase's initial implementation work.

## Proposed implementation slices

1. **Managed canonical type boundary.** Add the smallest schema/Core capability that lets one canonical Note type be Calendar-managed, hidden from ordinary planner type selection and default Notes feed behavior while retaining normal validation/storage guarantees.
2. **Temporal/Day Core primitives.** Deterministic date identity, virtual/materialized Day repository behavior, collision/idempotence checks, and strict date/range helpers.
3. **Temporal links and chronology.** Explicit Day links/backlinks plus the approved same-day `Added` heading grouping/navigation, keeping capture time separate from described/event time.
4. **Calendar v0 read/UI surface.** Month + Day projections over virtual/materialized Days, Journal temporal properties, explicit links, and useful semantic activity.
5. **Planner/routing integration.** Add the smallest model-facing specialized temporal-capture contract needed for natural requests, plus regression sentinels and one focused production-model gate only after deterministic behavior is settled.

Each slice must prefer existing Note/storage/link/history primitives over parallel Calendar implementations.

## Open decisions

None at product-contract level before implementation. Exact schema flag names, internal class/function names, URL/API shapes, and presentation details are implementation choices so long as they preserve this contract.

## Architecture challenge

Result: **PROCEED after approved reconsideration**.

The first hybrid proposal treated Calendar Days as Markdown resources outside the canonical Note type system. Review found that this would duplicate or special-case validation, links/backlinks, editing, history, and future direct-Markdown ingestion.

The approved simpler boundary keeps one canonical Markdown/Note substrate and introduces only the distinction between ordinary planner-selectable semantic types and an application-managed canonical type. `calendar_day` remains Calendar-owned and deterministically addressed, so the generic planner cannot create/search it as an ordinary entity while Calendar still reuses the existing authority and safety machinery.

The human explicitly approved this reconsidered boundary and the application principle that a selected app/capability may resolve its own bounded functionality deterministically or with a separately justified AI boundary. No additional product decision is required before implementation.
