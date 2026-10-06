# Calendar multi-day schedule view

Status: **implemented and deterministically validated on the current feature branch; isolated-DEV
mobile review is next**. Architecture challenge result: **PROCEED**. The earlier Calendar-v0 deferral
of an hourly grid is intentionally reconsidered because Tasks now supplies real structured timed work
and the user has explicitly requested the 1/3/7-day surface. The phase remains read-only and does not
create an Event model inside Calendar.

This phase adds a read-only hourly Calendar surface for **1, 3, or 7 consecutive days**. It reuses Odyssey's existing temporal evidence and application-owned scheduling metadata without creating an Event model inside Calendar. Structured Events remain a later capability and must be able to project onto the same surface without redesigning it.

## Product outcome

Calendar currently answers “what is associated with this day?” through month and Day views. The new surface answers: **“what is positioned in time across the next few days?”**

The user can choose 1, 3, or 7 days. The view contains a sticky date header, an all-day / no-exact-time lane, a vertically scrollable hourly grid, timed cards positioned from canonical exact-time evidence, horizontal swipe navigation by one full visible window, explicit previous/next controls, a Today control, and session-only persistence of the chosen 1/3/7 mode.

The existing Month view remains available and the existing rich Day detail remains the destination when a user opens a specific date.

## Temporal projection contract

Calendar owns presentation and deterministic temporal projection only. It does not infer times from free text and does not mutate Tasks, facts, or future Events.

The first schedule projection may include two currently grounded source families:

1. **Tasks**
   - `planned_start_at` is a timed start.
   - a same-day `planned_end_at` supplies the visual interval end.
   - an exact-time `deadline_at` may appear as a punctual deadline marker when it is not redundant with the task's planned start.
   - date-only `target_date` and date-only `deadline_at` belong in the all-day/no-exact-time lane.
   - `completed_at` is lifecycle history and is not projected into this planning-oriented grid.
   - when a Task has a timed planned start on a day, a same-day target-date marker is suppressed to avoid duplicate visual entries.

2. **Atomic facts with semantic `TemporalAnchor` evidence**
   - exact-time anchors become punctual timed entries;
   - date-only anchors become all-day/no-exact-time entries;
   - `recorded_at` capture time is not semantic occurrence time and must not position an item.

A punctual timed entry has an exact start but no semantic duration. The UI may give it a small minimum visual card height for legibility, but must not label or imply an invented end time. Only an actual canonical end coordinate may produce an interval.

Future Events can add lifecycle-owned timed occurrences to the same projection contract later. This phase must not define event recurrence, attendees, availability, event mutation, or reminder semantics.

## Query boundary

Add one bounded Calendar read operation for a consecutive range of **1, 3, or 7 days**. The browser must not issue seven independent Day scans for a 7-day view.

Conceptual public response:

```text
calendar_schedule
  start_date
  day_count
  days[]
    date
    all_day[]
      kind           task | fact
      source_id
      source_type
      label
      text?
      role?          target | deadline | semantic_date
    timed[]
      kind           task | fact
      source_id
      source_type
      label
      text?
      role?          planned | deadline | semantic_time
      start_time     HH:MM
      end_time?      HH:MM only when canonically grounded
```

The operation is provider-free, deterministic, and reads validated canonical Markdown through the existing Calendar/Core boundaries. No new persistence, index, service, or browser Markdown parsing is introduced.

## Browser behavior

The Calendar surface gains a small view selector: **Mes · 7 · 3 · 1**.

For 1/3/7 modes:

- days share one vertical time axis;
- the hourly viewport defaults to a useful daytime position but can scroll through the full day;
- timed cards use the existing semantic Note-type icon/color presentation;
- cards display the source Note name and compact grounded text when available;
- all-day items sit above the time grid and never receive invented clock positions;
- swipe left advances exactly `day_count` days and swipe right moves back exactly `day_count` days;
- navigation also has explicit previous/next buttons for accessibility and desktop use;
- tapping a date header opens the existing Calendar Day detail;
- tapping a Note-backed item may hand off to Notes using its stable `source_id`;
- the selected day count is session UI state only.

The first version does not implement drag/drop, resizing, creation, or direct schedule mutation.

## Acceptance criteria

1. 1-, 3-, and 7-day modes use one bounded schedule request per visible window.
2. Horizontal swipe moves by exactly the active window size; explicit previous/next does the same.
3. Today returns the visible window to today without creating knowledge.
4. Exact Task planned intervals are drawn at their actual start/end times.
5. Start-only Tasks and exact-time facts are displayed as punctual items without invented duration.
6. Date-only Task roles and date-only semantic facts appear only in the all-day lane.
7. Capture time (`recorded_at`) never becomes semantic schedule position.
8. The browser never parses Markdown or interprets natural language to obtain dates/times.
9. Month and existing Day views continue to behave unchanged.
10. Future Events can join the projection without Calendar taking Event lifecycle ownership.
11. Provider-free unit, application, transport, browser, swipe/navigation, and vertical Task/fact tests cover the new contract.

## Out of scope

- Event creation/lifecycle/recurrence;
- reminders or notifications;
- drag/drop scheduling;
- conflict detection or availability;
- timezone conversion policy beyond preserving canonical local wall-clock coordinates already stored with offset-aware timestamps;
- arbitrary user-selected day counts other than 1, 3, and 7;
- background calendar synchronization with external providers.
