# Post-UI-2 note creation and schema evolution exploration

Status: **Slices 1–2 are implemented. Slice 3 remains Draft: its focused planner gate passed, and its deterministic request-aware one-hop entity-context enrichment is implemented pending DEV human smoke evidence.**
Performance / Latency / Cost P1 is complete; UI-2 merged in PR #124.

## Why this exists

Once UI-2 makes canonical notes visible, normal DEV use can evaluate not only whether writes succeed, but whether Odyssey creates the *right knowledge shape* from ordinary narrative input and whether that shape remains useful when browsed later.

The first real narrative-style DEV exercises showed promising behavior (one event/journal-style note plus reusable entity notes, extraction of durable facts belonging to more than one entity, and useful explicit links), but they also exposed questions that should be investigated deliberately before moving on to broader application work.

A later real DEV exercise sharpened one concrete expected behavior: when the user explicitly states a durable fact that applies to a finite, resolvable set of people, that fact must become discoverable from every relevant entity. This does **not** necessarily require copying the same prose into every Markdown note. Prefer one canonical fact occurrence plus explicit links/backlinks and relevant mention context when that is sufficient for both human browsing and retrieval. Materialize duplicate per-entity prose only when there is a demonstrated retrieval/product need that cannot be satisfied by first-class relation context.

Example: after a prior journal entry establishes which named people were present, a follow-up such as “todos los que estaban ayer formamos parte del mismo grupo de amigos; fuimos al colegio juntos en la Escola Laia” should resolve the referenced people and make those facts visible/queryable from each corresponding person. The user must not need to create a separate `group` note merely for the facts to be reachable. This does not authorize inventing friendship or other relations from mere co-occurrence: the propagation rule applies only when the user has explicitly asserted the shared fact.

Likewise, when a fact is explicitly relational, Odyssey should make the relation usable from both relevant viewpoints. This may be achieved through the source note plus incoming/outgoing explicit links and mention context rather than duplicated prose. Retrieval over an entity therefore needs to consider the entity note together with relevant explicit incoming/outgoing relation evidence, subject to bounded ranking so a heavily linked entity does not inject unbounded context.

This follow-up is therefore a bounded product/architecture exploration, not an authorization to redesign the schema or add a second knowledge authority.

## Reference & Relationship Resolution v1

### Objective

Resolve a natural relational reference to one or more existing, canonical stable identities before
Odyssey considers CREATE. The user should be able to refer naturally to people already grounded by
explicit canonical relationship or participant evidence, without creating placeholder entities from
the surface wording. This v1 proves the generic mechanism; it does not introduce a broad social graph
or change the canonical note schema.

### User-visible behavior

- If canonical evidence establishes two known parents, a request referring to them as a relational
  plural resolves both people and never creates a note named after that phrase.
- If exactly one canonical person satisfies a singular relation, the reference resolves to that
  existing person. If more than one or none safely satisfies it, Odyssey clarifies rather than guess.
- A pronoun or relational phrase can use a uniquely resolved source entity. Recent conversation may
  identify that source wording, but the current canonical note/link evidence remains the only authority
  for the relationship and member set.
- A universal bounded-set reference resolves only the complete, finite, canonical participant set.
  The explicitly asserted shared fact is stored once on a natural existing canonical source and
  carries explicit links to every resolved member. If no natural source exists, Odyssey clarifies;
  it does not attach the fact to the user's person note or silently create a source/group/event note.
  Co-occurrence alone never creates friendship, partnership, kinship, or another relation.

The examples `mis padres`, `mi hija`, `sus hijos`, `su pareja`, and a prior event's participants are
acceptance illustrations, not a phrase list. The planner and Core contract must accept arbitrary
natural language and must not hardcode Spanish wording, kinship words, or named relation types.

### Smallest proposed contract

```text
natural relational mention
        |
        v
planner preserves relation/source/member-set intent
        |
        v
Core resolves a source identity, then enumerates only bounded,
current literal-link candidates and their explicit canonical fact blocks
        |
        +--> one grounded target / complete finite set -> stable IDs
        |
        `--> none, multiple, stale, or incomplete evidence -> clarification
        |
        v
existing target preflight + reference binding
        |
        v
one canonical fact occurrence with explicit links/backlinks
```

The candidate boundary is the existing canonical Markdown graph: validated current source notes,
literal outgoing/incoming wikilinks, and the exact visible fact blocks that contain them. Core must
validate paths, stable identities, source freshness, cardinality, and the final links. It must bound
the first slice to one source identity and one hop of literal evidence; it must not recursively walk a
graph, union arbitrary semantic candidates, or treat a backlink index as authority.

`KnowledgeReference` and the existing preflight/rendering table remain the preferred write hand-off.
Reference-only target units may reuse the current safe target-preflight path; the fact-bearing source
unit links to each already resolved target. This keeps one canonical occurrence and lets current
Markdown backlinks and bounded retrieval make the fact discoverable without mirrored prose or an
inverse write.

### Responsibilities

**Planner/model** preserves the relational wording, the source/reference intent, and whether the
request is singular or a bounded universal set. It may select among a Core-supplied, finite candidate
set only through the existing fail-closed contextual-resolution boundary. It does not assert a stable
identity, enumerate arbitrary vault members, decide that a relationship exists, create a placeholder
entity, choose a physical fact location, materialize Markdown, or infer an inverse/mirrored write.

**Deterministic Core** resolves the source through the existing self/existing-identity boundaries,
re-reads and validates canonical evidence, constructs the bounded eligible candidate set, enforces
singular versus complete-set cardinality, validates every resulting stable ID, and blocks CREATE until
relational resolution has finished. A relational surface phrase with no safe result is clarification,
not a new canonical name. Core renders only the existing `KnowledgeReference` markers into safe
wikilinks and preserves the current planner semantic validator and Sol fallback contract.

Recent conversation is referent evidence only: it can help identify which already-grounded source the
user means, but it cannot supply relationship membership, current facts, or a new relationship. The
canonical source must independently confirm every candidate before a write can use it.

### Backlink-enriched entity retrieval

V1 entity evidence may combine the entity's direct canonical facts/properties with every valid
one-hop incoming linked-fact snippet and, when needed, every valid one-hop outgoing relational fact
snippet in the supplied scope. This is a Core evidence projection over current Markdown, not a new
authority or an unrestricted graph query.

- Do not inject whole backlink source notes by default.
- Ground every selected snippet by re-reading and validating its current canonical Markdown source
  and confirming its literal wikilink resolves to the requested stable identity.
- Slice 1 returns every valid one-hop candidate in the supplied current canonical scope. Later
  request-aware retrieval, not the projector, selects final snippets for the actual `ContextPackage`;
  final-context limits are separate from the projector's structural one-hop scope. Derived link
  indexes may identify candidates only; they do not prove current facts.
- Keep one canonical fact occurrence sufficient when a linked snippet makes it discoverable from the
  related entity. For example, a linked employment fact in one person's note can support retrieval
  about the linked person without copying that sentence into the target person's note.
- Include outgoing snippets only when needed to answer the entity request; direct entity evidence
  remains first, and relationship evidence must be visibly distinguishable as coming from another
  canonical source.

This is entity-context enrichment for ordinary retrieval. It does not bring relational traversal or
general graph-aware query syntax to the UI-2 Notes search surface in v1.

### Relationship and traversal semantics

V1 treats a relationship as usable only when the relevant current canonical fact explicitly links the
two identities. A fact expressed from either viewpoint may be supplied as evidence for the same
relationship query, but v1 does not write an inverse fact, duplicate prose, infer a property of the
other person, or make relationships transitive. Symmetry/inversion therefore affects candidate
evidence selection only; it never creates new knowledge. The relation meaning must come from the
explicit fact and bounded request/candidate evidence, not from co-occurrence or a generic registry.

### Acceptance criteria

1. Deterministic fixtures prove singular and plural relational references resolve only to existing
   stable IDs backed by current canonical linked evidence.
2. A two-member parent example links both existing identities and creates no generic relation-named
   note; a unique child example links the known child and creates no placeholder person.
3. A source-relative plural example succeeds only when its finite participant set is completely
   grounded by canonical event/context evidence. Any unknown, ambiguous, duplicate, stale, or partial
   member evidence produces clarification and no CREATE.
4. The shared-fact result has one canonical fact occurrence plus explicit links to all members; UI-2
   backlinks and existing retrieval can discover it without repeated per-person fact prose.
5. Entity retrieval may receive direct note facts/properties and every valid one-hop incoming or
   outgoing linked-fact candidate in the supplied scope. Every candidate is re-grounded against
   current canonical Markdown and returned without whole source notes by default. The Core
   request-aware layer locally ranks and serializes final bounded source-provenanced snippets for
   the `ContextPackage`; tests prove a single canonical fact remains discoverable from the linked
   entity without copying it.
6. Backlink/index projections are candidate/transport aids only; stale, missing, malformed, or
   ambiguous evidence cannot establish identity or enter the candidate set or final context.
7. Direct current-fact retrieval, ordinary exact/semantic identity resolution, self binding,
   `KnowledgeReference` marker validation, link binding, pending-reference behavior, and UI-2 Notes
   detail/backlinks retain their existing fail-closed contracts.
8. The planner's semantic validator and Luna-to-Sol fallback behavior remain unchanged except for a
   separately reviewed, backward-compatible relational-intent extension. Deterministic tests alone do
   not validate a changed model-facing contract; a later implementation requires focused live evidence.

### Out of scope

- schema mutation, a relationship registry, typed-edge ontology, graph database, service, or second
  knowledge store;
- arbitrary-depth graph traversal, transitive/similarity-based relation inference, and automatic
  relationship or inverse-fact writes;
- graph-aware Notes search, relationship filters, general plural joins, group-note creation, fact
  deduplication, Daily notes, or schema management;
- product UI/clarification redesign, provider/model selection changes, request-type fast paths, and
  any production/DEV deployment or personal-data use.

### Regression and safety invariants

1. Canonical Markdown remains the sole current-knowledge authority; conversation, indexes, and
   backlinks remain evidence/projections only.
2. Exact stable identity is required before a link is rendered. A raw phrase, semantic score, or
   relation label never authorizes a target.
3. CREATE is considered only after relational resolution is exhausted. Generic relational wording is
   never a CREATE name.
4. Singular resolution is exactly one target. A universal finite set is all grounded members or a
   clarification; no partial attachment is silently persisted.
5. One-hop candidate selection is explicit and bounded. No transitive, inverse-write, or
   co-occurrence inference occurs.
6. No duplicate durable prose is introduced solely to make a fact discoverable from another entity.
7. Existing pending-work behavior remains available for unresolved references; no pending artifact is
   promoted to canonical knowledge.

### Proposed implementation slices

1. **Evidence and contract slice.** ✅ Implemented provider-free as a bounded Core projection over
   current validated Markdown. It returns a source-hash-bound fact locator, source/target stable
   identity and path provenance, literal-link target evidence, complete-or-empty finite sets, and
   complete direct/incoming/outgoing entity candidate set for the supplied scope. The later
   request-aware Core layer now locally ranks final source-provenanced `ContextPackage` snippets;
   Slice 1 itself still does not rank or count-truncate candidates. It does not modify
   `RequestPlan`, planner prompts, Notes search, or writes. Its contract covers one source identity
   and one literal-link hop. Provider-free fixtures prove one unique
   singular target, one complete finite set, and the bounded-current-Markdown retrieval projection
   (direct entity facts/properties plus a relevant incoming snippet and an outgoing snippet only when
   needed). This slice has no general graph query
   or Notes search traversal.
2. **Safe write integration.** ✅ Implemented provider-free with one Core-internal binding that
   re-grounds the source-hash-bound fact locator during write preparation, then admits only the
   exact complete current member-ID set into the ordinary preflight table as structurally
   reference-only no-write units. Each member binding pairs its unit index with a Core-grounded
   stable ID, so the new fact's reference order can differ from the evidence fact's literal-link
   order. The fact-bearing natural source must independently preflight as that exact existing note.
   Rendering and materialization therefore write one linked fact on that source only; stale,
   incomplete, mismatched, or source-less preparation raises before mutation.
3. **Relational planner contract, Core bridge, and focused model gate.** The Draft bridge adds an
   optional `SelectionCriteria.relational_reference` with only source-relative wording, source kind
   (`self` or `existing`), source query (`null` for self), and `one` versus `complete_set` semantics. It carries no
   stable ID, path, filename, relation type, or enumerated member set. Core resolves the source
   through existing self/existing-entity boundaries, selects one current outgoing or incoming fact
   from bounded one-hop evidence through the existing contextual candidate validator, and reprojects
   current Markdown.
   Singular READ restricts retrieval to the exact member and uses answer presentation only;
   singular fact-bearing WRITE passes only
   through a relationship-specific re-grounded preflight. Complete-set WRITE expands one planner
   fact into the existing Slice 2 source plus exact reference-only member binding; one source fact
   is written, and members remain unchanged. Complete-set READ resolves the same complete current
   member set and passes its exact stable IDs to existing `get_context(..., allowed_note_ids=...)`;
   existing retrieval and ranking remain responsible for answer evidence. Incomplete sets defer
   before retrieval, and relational note-set presentation remains separate. Ordinary preflight
   always clarifies on relational intent, preventing fallback CREATE. The planner's general
   `all_matching` remains separate.

   The Slice 3 architecture challenge returned **PROCEED**: an optional selection value plus a
   Core-owned resolver is the smallest fit; a new action type, relation ontology, or generic stable-ID
   override would add unnecessary authority. Synthetic deterministic tests cover singular read/write,
   complete-set source write, ambiguity, stale member, and ordinary regressions. The frozen focused
   model gate is [owned here](../../benchmarks/reference_relationship_v1/README.md). Its conservative
   ten-Luna-plus-one-Sol, 11-call ceiling is $0.458174. Attempt 1 at
   `2405b136fc9abe686efb49599ba6368e479fe71a` stopped before provider construction because its
   command environment lacked `OPENAI_API_KEY`, preserving a zero-row artifact. Attempt 2 at
   `e17b5f750573e39aebf8477e933902e083ad7f9f` then used a distinct artifact and verified child
   export: R01 and W01 passed Luna-only, but W02 returned `UNRECOGNIZED_REQUEST` rather than the
   required complete-set shared-fact write. The runner stopped fail-closed after three Luna calls
   ($0.00250944 actual cost), with no Sol fallback. The follow-up adds one non-evaluation Luna
   complete-set source-write teaching example with different wording; frozen cases/oracle and Core
   remain unchanged. Attempt 3 at `0c28855f35b39f4429ae2fc60db180a38fe3b9d6` passed R01, W01,
   W02, C01, P01, S01, and S02 Luna-only, including the required one-unit complete-set write for
   W02. W02 retained the expected `source_selector_review` flag. S03 reached a local Luna
   `KNOWLEDGE_UNIT` / `INVALID_FIELDS` validation failure, then passed via one Sol fallback; the
   runner flushed that row and stopped, leaving S04/S05 unattempted. Actual Attempt-3 cost was
   $0.05772924. Review accepts W02's natural-language `ayer` selector and S03's final ordinary
   Marta/Airbus `KnowledgeReference` plan as a valid production fallback. A fixed, unexecuted
   continuation selects only S04 then S05, has a $0.36979880 maximum for at most three calls, and
   requires new explicit authorization. The $0.37 authorization was recorded at
   `828672cc4597c1931853cf32d1fa90330eccf25b`; the continuation ran once at that same HEAD and
   passed S04/S05 Luna-only. S04 preserved ordinary `all_matching` tag-add semantics, and S05
   preserved two independent ordinary Marta facts. Its 2 Luna calls used $0.00216274 with no Sol
   fallback. All ten frozen cases now have reviewed evidence, so the focused Slice 3 model gate
   passed within the bounded v1 contract. Slice 3 remains Draft and v1 is not complete pending final
   human review and remote CI.
4. **Later, separately approved work.** Consider relationship traversal in Notes, richer relationship
   semantics, or a structured representation only if v1 evidence shows that explicit links and bounded
   source facts cannot meet a concrete user need.

### Architecture challenge

PROCEED after approved decisions

The challenge found a material boundary concern: existing `KnowledgeReference.role` is an in-plan
occurrence label, while canonical Markdown stores relationships as human-readable linked facts.
Treating either as a durable generic relation registry would silently add ontology and make model
interpretation a second identity authority.

The human-approved simpler alternative keeps canonical linked fact blocks and existing stable
identity/link binding as the evidence boundary. Core uses a one-source, one-hop, finite-candidate
projection and the current fail-closed resolution path; it persists only the asserted fact and its
ordinary links.

The approved v1 trade-offs exclude unrestricted graph questions, arbitrary relationship algebra, and
automatic inverse materialization. An explicit linked fact from the opposite viewpoint may ground
resolution/retrieval, but does not create mirrored prose, transitive relations, or property inheritance.
Universal references use all-or-clarify. Shared facts stay at an existing natural source; if none is
clear, the system clarifies.

The implementation should begin with the narrow evidence-and-contract slice above. Keep entity
retrieval enrichment to bounded current fact snippets; do not add a registry, schema field, graph
store, or general traversal engine.

Human decision required: NO — the v1 product choices below have been approved. Routine implementation
details remain subject to the existing tests and safety contracts.

### Approved v1 decisions

1. **Relationship evidence:** a current explicit canonical Markdown fact with a validated literal
   wikilink is sufficient v1 evidence. Do not add schema-structured relationship semantics, a
   relationship registry, typed-edge ontology, or graph database.
2. **Shared-fact home:** prefer an existing natural canonical source—an event/journal/source note
   when the fact arises there, or an entity note when that entity is the natural subject. If no
   natural home exists, clarify. Do not silently attach the fact to the authenticated user's person
   note or create a group/event/source note.
3. **Inverse/symmetric evidence:** an explicit linked fact written from the opposite viewpoint may
   ground resolution and retrieval. Do not write mirrored/inverse duplicate prose, infer transitive
   relationships, or propagate unrelated properties.
4. **Universal/bounded sets:** use all-or-clarify. A universal reference succeeds only when its
   complete bounded grounded set resolves; never attach a fact to only the resolvable subset. An
   explicit reviewed partial-set UX is outside v1.
5. **Backlink-enriched retrieval:** entity evidence may contain direct canonical facts/properties and
   every valid one-hop incoming/outgoing linked-fact candidate in the supplied scope. Re-ground each
   candidate against current Markdown and do not inject entire backlink source notes by default.
   Later request-aware retrieval selects the final bounded context. A single linked canonical fact
   remains sufficient; do not copy it to another note only to make it retrievable.

No open product decision remains before implementation of this v1 scope. Any proposed expansion beyond
these approved decisions returns for human review. The following sections remain broader post-UI-2
exploration and do not expand this v1 contract.

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

- With known parents Juan and Ana, `Quiero comprarles unas entradas a mis padres` should stay on an existing natural canonical source and link to **both Juan and Ana** so bounded backlink retrieval can expose the fact from either person. If no natural source exists, clarify; do not silently choose the user's own note or create a new note.
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

P1 closed the observed Luna→Sol fallback as a local validation mismatch and then removed duplicated
Luna Structured Outputs schema material. The [P1 closeout](performance-cost-p1.md#closeout-decision)
records the resulting input and latency evidence and the decision to stop optimization. Backlink,
context, and reference-resolution work follows that decision and must not become a performance
baseline oracle or introduce a request-specific fast path.

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
Reference & Relationship Resolution v1
        |
        +--> reference/kinship/group resolution before entity creation
        +--> bounded shared-fact links/backlinks
        |
        v
remaining note-creation + schema-evolution exploration
        |
        +--> symmetric/inverse relationship semantics beyond v1
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
