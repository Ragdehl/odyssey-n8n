# Post-UI-2 note creation and schema evolution exploration

Status: **planned after Performance / Latency / Cost P1; UI-2 merged in PR #124**.

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

### Reference, kinship and bounded-set resolution

Real mobile use exposed an important class of natural references that Odyssey must resolve before creating new entities or writing durable facts.

Examples include:

- `mis padres` after the user's parent relationships are already known;
- `mi hija` when a unique known daughter can be resolved;
- `todos los que estaban ayer`, where a prior event/journal context already identifies the bounded participant set;
- `todos los del grupo`, when the current/recent context identifies the relevant people;
- relational phrases such as `sus hijos`, `su pareja`, or `mis compañeros` when the source entity and relation are already grounded.

Expected direction:

1. Resolve the reference against known canonical identities and explicit relationships/context before considering CREATE.
2. If the reference resolves to one or more stable entities, preserve explicit links to those entities in the durable fact even when the fact remains physically stored on another note.
3. Do not create generic canonical entities such as `mi hija`, `mis padres`, `todos los del grupo`, or `su pareja` merely because the surface phrase appeared in prose.
4. If a singular relational phrase is genuinely ambiguous (for example several known daughters and no further evidence), fail closed/clarify rather than guessing.
5. Plural references may legitimately resolve to a bounded set; the writer/link binder must be able to bind all resolved targets, not just the first one.

Concrete acceptance examples for the exploration:

- With known parents Juan and Ana, `Quiero comprarles unas entradas a mis padres` may remain a fact on the user's own note or another appropriate canonical note, but the fact must link to **both Juan and Ana** so their backlinks/retrieval expose the information.
- With one uniquely known daughter Chloe, `Quiero comprarle X a mi hija` should resolve `mi hija` to Chloe and must **not** create a new person note named `mi hija`.
- After an event establishes named attendees, `Todos los que estaban ayer fuimos juntos al colegio Laia` should bind the shared fact to the resolved attendee identities through explicit links/context rather than leaving only unlinked prose.

The objective is not broad commonsense inference. Resolution must remain evidence-grounded, identity-safe, deterministic where possible, and fail closed when the relation/reference is not sufficiently grounded.

### Relationship semantics: symmetric, inverse, and non-inferable

The exploration should explicitly distinguish relation semantics instead of relying on the model to rediscover them ad hoc.

Examples:

- **Symmetric relation**: if an explicit fact states that A is married to B, the relationship is usable from B's viewpoint as married to A. Explicit friendship and coworker relationships may also be symmetric when that is the declared relation/context.
- **Inverse relation**: `A is daughter of B` and `B is parent of A` are two viewpoints over the same grounded relationship, not two unrelated facts.
- **Non-inferable relation**: `A lives in Calonge` plus `B is A's partner` does **not** establish that B lives in Calonge.
- **Non-transitive relation**: `A knows B` and `B knows C` does **not** establish that A knows C.
- **Co-occurrence is not relationship**: being at the same meal/workplace/event does not by itself establish friendship/coworker status unless the user explicitly states it.

The representation may remain textual/link-based initially; a formal relation registry should only be introduced where it materially improves deterministic behavior. Whatever representation is chosen, retrieval and browsing must expose grounded symmetric/inverse viewpoints without forcing duplicated prose that can drift.

### Relational / graph-aware Notes search

The Notes intelligent-search surface also exposed a distinction between semantic text search and relationship traversal.

A query such as:

`Hijos de Lara`

should be able to resolve `Lara` as an entity, inspect explicit grounded relationship/link evidence such as `Sus hijas se llaman [[Aura]] y [[Enia]]`, and return the **target person notes Aura and Enia**. It should not require an artificial schema filter when the user intent is relationship traversal.

The post-UI-2 exploration should therefore define how planner/retrieval represents bounded relation-following queries without turning the browser into a graph engine or making backlinks a second authority. Exact explicit links and canonical relation evidence should be preferred over open-ended inference. The same mechanism should support queries such as spouse/partner, children, parents, collaborators or explicitly stated group membership when the source evidence is present.

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

Real narrative input exposed a Luna→Sol fallback that made an everyday write feel slow. The
[Performance / Latency / Cost P1 contract](performance-cost-p1.md) owns the measurement gaps, frozen
cases, budget, and evidence-driven optimization rule. Backlink/context and reference-resolution work
follows P1 and must not become a performance baseline oracle.

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

## D. Notes presentation and browsing follow-ups

### Controlled tag filtering

The mobile filter review showed that tags should not normally be entered as arbitrary free text. The future Notes filter UX should present **existing canonical tags** as controlled selectable values (for example searchable chips/multiselect when the list is large). Creating a new tag, if supported, is a separate knowledge/schema action and must not happen implicitly merely because a user typed an unknown value into a filter.

### Negative / exclusion filters

A future Notes filter algebra should support bounded **exclusion** use cases such as `all except February`, `type is not X`, or `tag does not contain Y` without forcing the user to select every allowed value manually.

Product constraints:

- exclusion must remain understandable on mobile (for example an explicit Include/Exclude mode or clear negative chips rather than hidden boolean logic);
- Core owns the filter semantics; the browser must not invent its own NOT interpretation;
- define how exclusion combines with multiple values and ranges before implementation;
- avoid an unrestricted boolean-query builder unless real use demonstrates the need;
- planner-inferred negative filters must remain visible/editable/removable just like positive inferred filters.

### Derived human-readable note view

Canonical Notes intentionally expose atomic facts and backlinks because that representation is precise and useful for editing/retrieval, but it can be visually mechanical for ordinary reading. Explore an optional user-triggered **readable view** that is a derived presentation layer over the canonical facts/relationships.

Desired contract:

- Canonical Markdown/facts/backlinks remain the authority.
- A button or view toggle may generate a fluent human-readable rendering from the note's own facts plus bounded relevant relationship/backlink evidence.
- The generated view must preserve Odyssey links/identity navigation rather than flattening entity references into plain text.
- The generation step must not add new knowledge, make unsupported deductions, or silently mutate canonical facts.
- The generated presentation may be cached for fast later reads.
- Cache validity should depend on the effective evidence projection (direct facts/properties plus relevant links/backlinks) and generator/version, not only on the note file's own modification time. A new relevant incoming fact may therefore invalidate the readable cache even if the target Markdown file itself did not change.
- If evidence changes, the cached readable view becomes stale and should be regenerated lazily or explicitly rather than presented as current.
- The original fact-oriented view must always remain available.

This should remain a presentation/cache capability, not a second personal-knowledge authority.

## E. Product questions to observe rather than decide now

Do not decide during UI-2 whether Chat or Notes should become Odyssey's primary landing surface.

Real use may reveal a useful division of labor:

- **Notes** for browse/search/filter/navigation/read/discovery;
- **Chat** for synthesis, complex questions, natural knowledge capture, mutation commands, and future schema/capability management.

Collect real-use evidence before changing navigation priority or removing/reducing either surface.

## Sequence

```text
UI-2 read-only Notes merged
        |
        v
Performance / Latency / Cost P1
        |
        v
bounded note-creation + schema-evolution exploration
        |
        +--> reference/kinship/group resolution before entity creation
        +--> symmetric/inverse relationship semantics
        +--> relationship traversal + graph-aware Notes search
        +--> knowledge distribution / backlinks / entity-note quality
        +--> exact + semantic fact deduplication and correction semantics
        +--> controlled tags + negative-filter Notes polish
        +--> readable derived-note presentation/cache contract
        +--> date/day navigation + Daily-note semantics
        +--> conversational schema-management contract
        |
        v
only then decide implementation slices and resume broader application roadmap
```

This document records the intended immediate follow-up only. It does not authorize schema mutation, production changes, provider/model changes, planner fast paths, relation inference, unrestricted boolean filtering, or generated-readable-note persistence as personal knowledge by itself.
