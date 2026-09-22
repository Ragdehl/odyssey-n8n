# Post-UI-2 note creation and schema evolution exploration

Status: **planned immediately after UI-2 closes; do not expand UI-2 scope to implement this work**.

## Why this exists

Once UI-2 makes canonical notes visible, normal DEV use can evaluate not only whether writes succeed, but whether Odyssey creates the *right knowledge shape* from ordinary narrative input and whether that shape remains useful when browsed later.

The first real narrative-style DEV exercises showed promising behavior (one event/journal-style note plus reusable entity notes, extraction of durable facts belonging to more than one entity, and useful explicit links), but they also exposed questions that should be investigated deliberately before moving on to broader application work.

A later real DEV exercise sharpened one concrete expected behavior: when the user explicitly states a durable fact that applies to a finite, resolvable set of people, that fact must become discoverable from every relevant entity. This does **not** necessarily require copying the same prose into every Markdown note. Prefer one canonical fact occurrence plus explicit links/backlinks and relevant mention context when that is sufficient for both human browsing and retrieval. Materialize duplicate per-entity prose only when there is a demonstrated retrieval/product need that cannot be satisfied by first-class relation context.

Example: after a prior journal entry establishes which named people were present, a follow-up such as “todos los que estaban ayer formamos parte del mismo grupo de amigos; fuimos al colegio juntos en la Escola Laia” should resolve the referenced people and make those facts visible/queryable from each corresponding person. The user must not need to create a separate `group` note merely for the facts to be reachable. This does not authorize inventing friendship or other relations from mere co-occurrence: the propagation rule applies only when the user has explicitly asserted the shared fact.

Likewise, when a fact is explicitly relational, Odyssey should make the relation usable from both relevant viewpoints. This may be achieved through the source note plus incoming/outgoing explicit links and mention context rather than duplicated prose. Retrieval over an entity therefore needs to consider the entity note together with relevant explicit incoming/outgoing relation evidence, subject to bounded ranking so a heavily linked entity does not inject unbounded context.

This follow-up is therefore a bounded product/architecture exploration, not an authorization to redesign the schema or add a second knowledge authority.

## A. Creation behavior from natural narrative input

Use realistic but disposable/synthetic DEV examples to inspect how one narrative request is decomposed into canonical notes and facts.

Questions to answer:

- When should Odyssey create an event/journal note versus only updating existing entities?
- Which durable facts should live directly on an entity note and which can remain once in another canonical note while still being reliably surfaced through explicit links/backlinks?
- When a sentence contains facts about several entities, does Odyssey make those facts discoverable from the correct canonical entities without unnecessary duplication?
- When one explicit durable fact applies to several resolvable people, can Odyssey preserve a single canonical occurrence while making it visible/queryable from every affected entity?
- Does explicit relational language become durable link/relationship knowledge without requiring the user to phrase the input unnaturally?
- Does Odyssey correctly avoid inventing stronger relations from mere co-occurrence (for example, people attending the same event must not automatically become `friends`)?
- When an explicitly stated durable relationship is present, does it survive as queryable knowledge from both relevant entity viewpoints rather than only as prose in the source narrative?
- Does follow-up language such as “todos los que estaban ayer...” correctly resolve the bounded participant set from prior context before attaching the new shared fact?
- Are newly created identity-only notes still useful and readable before they accumulate their own direct body facts?
- Can later retrieval answer both entity-centric questions and event-centric questions from the resulting graph of notes/links?
- Can retrieval include relevant incoming-link context without pulling every backlink or entire source note into the model context?

### Fact deduplication and correction

Real DEV notes also exposed two distinct duplicate patterns that must be handled deliberately:

1. **Exact duplicate** — the same fact text is appended more than once (for example the same partner fact repeated verbatim). Historical unsafe retries can create this, but future writes should also defend against exact duplicate fact insertion.
2. **Semantic duplicate/paraphrase** — two different strings express the same durable fact (for example “Mi mujer es X” and “Mi mujer se llama X”). Text equality is insufficient here.

The follow-up should define a bounded fact-equivalence policy that:

- prevents exact duplicate insertion deterministically where possible;
- detects high-confidence semantic equivalence before appending a new durable fact;
- preserves genuinely different facts even when they share vocabulary;
- does not collapse time-varying facts that are true at different dates;
- treats explicit corrections as updates/supersession rather than silently retaining contradictory duplicates;
- preserves provenance/auditability even when the visible knowledge is deduplicated;
- does not require broad whole-vault semantic comparison for every write if a cheaper target-note/local comparison is sufficient.

Prefer evidence from realistic narrative inputs over synthetic micro-prompts, but keep this work isolated from the real production vault until the behavior is understood.

### Date/day navigation and Daily-note exploration

A later mobile Notes review suggested a more compact temporal navigation model than long generated journal titles such as “entrada de diario de ayer sobre la comida en casa de Meritxell”. Explore whether Odyssey should expose a canonical day-level surface, for example a Daily note or equivalent date view, so date-oriented journal knowledge can be reached through a concise date-first label.

Questions to answer:

- Should one calendar day have one canonical Daily note, a virtual date view, or a lazily materialized Markdown note only when useful?
- Should journal entries primarily surface through their `entry_date`/day rather than generated narrative titles when displayed in compact lists and backlinks?
- When a date is navigationally meaningful, can its rendered date become a clickable Odyssey link to that day surface?
- Can notes/facts explicitly associated with a day link to that day so the day surface's backlinks naturally collect the people, events, journal entries, tasks, and other notes connected to it?
- How should this interact later with Calendar/Events without conflating `Task`, `Event`, `Reminder`, journal entries, and day navigation?
- Avoid blindly materializing a Daily note for every literal date appearing in prose or properties (for example a birth date). A date literal may be historical data rather than an intended day-navigation relationship; define the explicit semantics before automatic linking/creation.

The desirable product property is that a user can move naturally between an entity/event and its relevant day, while the same link/backlink machinery remains authoritative and rebuildable. Do not implement this inside UI-2.

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
        +--> knowledge distribution / relations / backlinks / entity-note quality
        +--> exact + semantic fact deduplication and correction semantics
        +--> date/day navigation + Daily-note semantics
        +--> narrative-write planner optimization investigation
        +--> conversational schema-management contract
        |
        v
only then decide implementation slices and resume broader application roadmap
```

This document records the intended immediate follow-up only. It does not authorize schema mutation, production changes, provider/model changes, or planner fast paths by itself.
