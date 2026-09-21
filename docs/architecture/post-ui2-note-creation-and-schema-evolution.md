# Post-UI-2 note creation and schema evolution exploration

Status: **planned immediately after UI-2 closes; do not expand UI-2 scope to implement this work**.

## Why this exists

Once UI-2 makes canonical notes visible, normal DEV use can evaluate not only whether writes succeed, but whether Odyssey creates the *right knowledge shape* from ordinary narrative input and whether that shape remains useful when browsed later.

The first real narrative-style DEV exercises showed promising behavior (one event/journal-style note plus reusable entity notes, and extraction of durable facts belonging to more than one entity), but they also exposed questions that should be investigated deliberately before moving on to broader application work.

This follow-up is therefore a bounded product/architecture exploration, not an authorization to redesign the schema or add a second knowledge authority.

## A. Creation behavior from natural narrative input

Use realistic but disposable/synthetic DEV examples to inspect how one narrative request is decomposed into canonical notes and facts.

Questions to answer:

- When should Odyssey create an event/journal note versus only updating existing entities?
- Which durable facts should be copied/materialized onto the relevant entity note rather than remaining only in the event/narrative note?
- When a sentence contains facts about several entities, does Odyssey distribute those facts to the correct canonical notes?
- Does explicit relational language become durable relation/link knowledge without requiring the user to phrase the input unnaturally?
- Does Odyssey correctly avoid inventing stronger relations from mere co-occurrence (for example, people attending the same event must not automatically become `friends`)?
- When an explicitly stated durable relationship is present, does it survive as queryable knowledge rather than only as prose in the source narrative?
- Are newly created identity-only notes still useful and readable before they accumulate their own body facts?
- Can later retrieval answer both entity-centric questions and event-centric questions from the resulting graph of notes/links?

Prefer evidence from realistic narrative inputs over synthetic micro-prompts, but keep this work isolated from the real production vault until the behavior is understood.

## B. Planner latency and cost for everyday writes

Real narrative input exposed an unacceptable-feeling interaction latency when Luna failed and bounded Sol fallback carried the planning request. This class of input is expected to be common, so planner cost/latency must be investigated after UI-2 instead of remaining indefinitely deferred.

The investigation should separate:

1. prompt/token overhead;
2. Luna structural/semantic failure rate on long narrative writes;
3. Sol fallback frequency and incremental cost;
4. planner time versus downstream contextual-resolution/write/index-refresh time;
5. whether safe deterministic preprocessing or request-class specialization can reduce planner burden without weakening the single validated planning authority;
6. whether the planner can consume a smaller schema/capability projection for common write classes;
7. whether repeated provider work can be eliminated without introducing hidden retries or a second planner.

Do not optimize by silently weakening validation, skipping entity/reference safety, or allowing ambiguous writes. Any fast path must retain the same fail-closed semantics and be justified by measured real-use evidence.

## C. Conversational schema understanding and management

A future Odyssey capability should let the user talk naturally with Odyssey about the note model itself, including:

- which note types currently exist;
- what each type means;
- which properties belong to each type;
- which properties are filterable and how;
- creating a new note type;
- renaming or otherwise modifying an existing type where safe;
- adding/modifying/removing type properties;
- deleting a type when safe and explicitly authorized.

This must not be implemented as ad-hoc browser-only schema editing. The canonical schema remains authoritative.

Before implementation, define explicit mutation semantics for schema changes, including:

- validation of proposed type/property definitions;
- compatibility with existing canonical notes;
- migration requirements when removing/renaming/changing a property or type;
- what happens to indexes/capabilities after a schema change;
- rollback/audit evidence;
- confirmation requirements for destructive changes;
- fail-closed behavior when existing notes would become invalid;
- distinction between changing the schema and changing the type of one existing note.

Natural-language Chat may be the user-facing control surface, but schema mutation must pass through one typed, validated Core capability rather than granting the planner or browser direct authority over `config/note-schema.json`.

## D. Product questions to observe rather than decide now

Do not decide during UI-2 whether Chat or Notes should become Odyssey's primary landing surface.

Real use may reveal a useful division of labor:

- **Notes** for browse/search/filter/navigation/read/discovery;
- **Chat** for synthesis, complex questions, natural knowledge capture, mutation commands, and future schema/capability management.

Collect real-use evidence before changing navigation priority or removing/reducing either surface.

## Sequence

```text
finish UI-2 read-only Notes
        |
        v
bounded note-creation + planner-cost/latency exploration
        |
        +--> knowledge distribution / relationships / entity-note quality
        +--> narrative-write planner optimization investigation
        +--> conversational schema-management contract
        |
        v
only then decide implementation slices and resume broader application roadmap
```

This document records the intended immediate follow-up only. It does not authorize schema mutation, production changes, provider/model changes, or planner fast paths by itself.
