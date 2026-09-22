# Future Events / Calendar capability

Status: **preserved product direction; prioritized after Tasks proves the minimum application contract**.

## Why this capability exists

Odyssey needs to distinguish information that **happens at a time** from information that represents
an **action to complete**.

A practical motivating case is a pasted school-year schedule containing a mixture of:

- one-day events;
- multi-day periods;
- recurring weekly sessions within a date range;
- contextual instructions attached to an event, such as a dress code or material to bring;
- possible follow-up actions or reminders that are related to an event but are not the event itself.

Today Odyssey can preserve such material as canonical knowledge, for example as a `document`, but the
current canonical schema has no structured `event` type or calendar capability. The future product
should not solve that gap by pretending every dated occurrence is a task.

Events / Calendar is intentionally treated as a **high-priority product capability adjacent to the
Core experience**, even if it remains an application/capability rather than Core knowledge
semantics. After read-only Notes and the first real Tasks application, calendar/event behavior is a
near-term priority because it turns durable personal knowledge into useful time-aware daily behavior.

## Semantic boundary: Task vs Event vs Reminder

These concepts must remain separate even when they compose naturally.

```text
Task
    something to do
    -> pending / completed lifecycle

Event
    something that happens at a date/time or over an interval
    -> occurrence / schedule semantics

Reminder
    a notification to surface at a chosen time
    -> delivery semantics
```

Examples:

```text
Event      "Class photo — 22 September"
Task       "Prepare the signed photo form"
Reminder   "Remind me the evening before the class photo"
```

An event must not become a task merely because it has a date. Likewise, a reminder is not the
canonical representation of the event it points to.

## Composition direction

Tasks remains the first real Odyssey application because it is the smallest practical way to prove
application routing, state, and composition. Events / Calendar should follow once Tasks has
established that minimum contract rather than expanding Tasks into a mixed task/calendar system.

A useful capability relationship is:

```text
Projects -> Tasks
             |
             v
         Reminders

Events ------+
```

Both Tasks and Events may use the lower-level Reminders capability. Projects may compose over Tasks.
The user should not need to understand this internal composition.

The current product priority is deliberately:

```text
UI-2 read-only Notes
        |
        v
Tasks — prove the minimum application contract
        |
        v
Events / Calendar — high-value time-aware capability
        |
        v
Reminders integration where Tasks/Events need delivery semantics
        |
        v
bounded maintainability checkpoint before secondary app expansion
```

Projects remains a committed direction, but it does not need to precede Events / Calendar. Real use
may still adjust the exact boundary between Events and Reminders, and the
[Functional Roadmap](functional-roadmap.md) remains the canonical owner of current sequencing.

Normal interaction remains natural-language-first. Optional explicit routing may exist when useful,
but the user should be able to paste a schedule or say "recuérdame el día antes" without choosing an
application first.

## Bounded proactive attention direction

The long-term product goal goes beyond a passive calendar/reminder database. Odyssey should be able
to provide **bounded, expected, context-aware proactive assistance** when durable evidence, current
state, user preferences, and explicit permissions make that useful. This is a product direction to
design later, not authorization to create reminders or event state automatically today.

A useful autonomy ladder to preserve for the later Events/Reminders product-definition phase is:

```text
observe / infer possible follow-up
        |
        v
suggest an appropriate reminder or action
        |
        v
create or schedule automatically only when an approved user rule/policy authorizes it
        |
        v
re-surface intelligently while the underlying item is still unresolved
```

The later design should explicitly distinguish these levels instead of treating every inference as
permission to mutate durable state. In particular, Odyssey may recognize that something probably
deserves follow-up without silently creating a reminder unless the user has authorized that class of
behavior.

Context-aware triggers may eventually combine evidence such as:

- absolute or relative time;
- weekday, workday, or useful time windows;
- task/event status and deadlines;
- user-known routines and schedules;
- location or arrival/departure context once location access is separately designed, permissioned,
  privacy-bounded, and reliable enough;
- dependencies or preparation lead time before another task/event;
- whether a previous notification was acknowledged, postponed, ignored, completed, or cancelled.

For example, a durable intention such as "I need to talk to Pierre about this at work" could support
a suggestion or, under an already-approved user rule, a reminder when the user is at work during a
useful workday window rather than forcing the user to invent an arbitrary clock time. A pending
preparation task for a Friday event should be surfaced while there is still useful time to act, not
merely at the event start. A reminder ignored once must not be treated as completed, but repeated
surfacing must remain bounded rather than becoming notification spam.

Proactive behavior should therefore be designed around **usefulness versus interruption cost**, not
raw reminder count. Likely future controls/constraints include:

- quiet hours and maximum notification frequency;
- grouped/digest delivery for low-urgency items;
- bounded escalation or adaptive re-notification for still-pending items;
- suppression when the related task/event is completed, cancelled, or no longer relevant;
- user-adjustable categories of proactive behavior;
- explicit permission boundaries for location or other contextual sensors;
- inspectable explanations such as why Odyssey surfaced an item now;
- easy feedback such as "not now", "don't remind me about things like this", or a durable preference
  that authorizes future similar behavior.

The governing product principle is: **proactive must not mean unpredictable**. The user should be able
to understand why an intervention happened and retain control over whether similar interventions are
suggested, automatically scheduled, re-surfaced, grouped, or disabled.

Potential future scenarios to challenge explicitly include:

- arrival/departure/location-aware reminders;
- workday/routine-aware reminders instead of only fixed timestamps;
- missed or overdue task follow-up with adaptive timing;
- dependency/preparation reminders before an event deadline;
- travel/lead-time awareness when reliable location/travel evidence exists;
- suppression after completion/cancellation;
- grouped low-urgency reminders instead of many interruptions.

None of these scenarios fixes the later architecture or autonomy policy. The Events/Reminders phase
must resolve with the human when Odyssey may **suggest**, when it may **create automatically**, when it
may **re-notify**, what evidence/confidence is sufficient, and which behaviors require explicit user
rules or permissions.

## Preserve source knowledge as well as structured events

Structuring a schedule must not destroy the original source material.

A future ingestion flow may look conceptually like:

```text
original pasted schedule / source document
                |
                +--> durable source knowledge
                |
                `--> structured event occurrences
                         |
                         +--> optional derived Tasks
                         `--> optional Reminders
```

The source can contain context that a normalized event record may not capture completely. Preserve
that source for traceability and retrieval rather than replacing it with generated event objects.

Tasks or reminders derived from an event should be created only when the user's intent supports that
action. Future explicit user rules/policies may authorize bounded automatic reminder behavior, but
Odyssey must not silently infer "buy", "prepare", or "notify" actions merely because an event contains
contextual text.

## Future event semantics

A later architecture challenge should define the smallest useful event contract. Likely concerns
include:

- stable event identity;
- all-day versus timed events;
- start/end date or date-time;
- local timezone when time is meaningful;
- multi-day intervals;
- bounded recurrence, such as Mondays and Tuesdays within a date range;
- source-note linkage / provenance;
- optional relationship to Tasks and Reminders;
- safe update/correction semantics when the source schedule changes.

Do **not** add these fields or a new `event` type to `config/note-schema.json` merely from this future
direction. A material schema change still requires an explicit proposal, compatibility/migration
review, deterministic validation, and human approval under `AGENTS.md`.

## Date interpretation and fail-closed behavior

Calendar data is especially sensitive to incorrect normalization. Future event extraction must fail
closed rather than inventing chronology.

Important cases include:

- a date whose year is omitted;
- localized month/day notation;
- an interval with no explicit times;
- recurring weekdays bounded by a date range;
- school-year or seasonal context that may imply a year but is not explicit enough to assume safely;
- ambiguous recurrence exceptions or holidays.

The normalized event can be structured only when the chronology is sufficiently supported. The
original text should remain available even when full normalization is not possible.

## Product scenarios to preserve

The future capability should support questions/actions such as:

```text
"¿Qué eventos del colegio hay en noviembre?"
"¿Cuándo empieza el ciclo de piscina?"
"¿Qué hay la semana del 12 de octubre?"
"Recuérdame el día antes de las olimpiadas."
"Añade como tarea preparar lo necesario para la excursión."
```

A useful future acceptance fixture should contain, using entirely synthetic data:

1. at least one single-date event;
2. at least one multi-day event;
3. at least one bounded recurring series;
4. contextual event information that must remain attached to the source/event;
5. an explicitly requested task derived from an event;
6. an explicitly requested reminder derived from an event;
7. at least one suggestion-only proactive scenario where no reminder is silently created;
8. at least one context-aware authorized reminder scenario, using synthetic time/location/routine data;
9. at least one ignored-but-still-pending item that may be re-surfaced without unbounded nagging;
10. at least one completed/cancelled item whose future reminder delivery is suppressed.

The fixture should prove that Events, Tasks, Reminders, notification delivery, and source knowledge
remain distinct while still composing correctly.

## Explicitly deferred

This direction does not yet commit Odyssey to:

- external Google/Apple/Outlook calendar synchronization;
- invitations, attendees, RSVP, availability, or meeting scheduling;
- a dedicated calendar UI before the event contract proves it is useful;
- unrestricted recurrence-rule support;
- automatic task creation from every event;
- automatic reminders for every event or every inferred follow-up;
- unrestricted/background location tracking or any location use without explicit product/privacy
  design and user permission;
- Projects or a generic plugin platform as a prerequisite for Events / Calendar.

Whether Events becomes a dedicated application, a lower-level capability with an optional calendar
surface, or a combination of both should be decided from the Tasks implementation and real Odyssey
usage rather than fixed prematurely.
