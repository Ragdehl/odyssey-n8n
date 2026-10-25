# Post-UI-2 note creation and schema evolution exploration

Status: **Historical v1 contract plus approved new conversational-schema design in section C.** Previous Slices 1–3 merged in PR #133; the current implementation status belongs in the [Functional Roadmap](functional-roadmap.md).
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
   `all_matching` remains separate. Fact references may use the same bounded singular anchor when
   their identity is defined by current canonical membership in self or an existing source. Their
   full descriptive query supplies only the qualifier applied inside that member set; `members` is
   always `one`, no stable identity is model-supplied, and failure to ground the declared anchor
   stays fail-closed rather than falling back to global semantic candidates.

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
- which natural-language queries a property supports, without asking the user to configure a technical `filterable` switch;
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

### Decisiones de producto confirmadas el 24-10-2026

- **IA asistida, no editor técnico:** en «Modelo de notas», desde Notes o Chat,
  conversación y vista previa como una nota; explicaciones y ejemplos de valor
  para el usuario antes de crear tipos. Reutilizar el tipo/propiedad existente
  si resuelve la necesidad; evitar duplicados semánticos.
- **Cualquier propiedad nueva será consultable** mediante las operaciones
  adecuadas a su valor; no mostrar «filtrable» al usuario. Primera prueba
  prevista: nacimiento de una persona con precisión parcial, sin inventar
  componentes ni duplicar la edad calculable.
- **Una confirmación** publica un cambio compatible de esquema y autoriza
  inspeccionar/rellenar propiedades con evidencia clara, en segundo plano.
  Las nuevas identidades descubiertas tras crear un tipo se proponen y
  confirman **en lote, por separado**.
- **Propiedad nueva:** enriquecer notas existentes de ese tipo. **Tipo nuevo:**
  buscar menciones de posibles entidades en hechos de todas las notas y
  proponer notas nuevas; nunca reclasificar una nota ya existente.
- **Sin previsión de tipos futuros:** `PendingReference` solo responde a
  referencias realmente irresueltas. La búsqueda retrospectiva comienza
  *cuando se aprueba el nuevo tipo*, no durante cada captura cotidiana.

La especificación técnica de estas decisiones y el orden de implantación
están en el contrato siguiente. **Nada de ello está implementado todavía.**

### Contrato de implementación acordado para la siguiente fase (24-10-2026)

**Objetivo único.** Que cualquier usuario describa en lenguaje natural la
necesidad de un tipo o propiedad y Odyssey reutilice su modelo actual siempre
que baste. Preferir la intención ya interpretada por C1/Chat y el contrato de
Core antes que añadir otro clasificador o agente. Superficie «Modelo de notas» en Notes, enlazada por los botones de
tipo ya visibles y accesible desde Chat; IA asiste a elaborar una propuesta y
muestra una tarjeta tipo Nota con nombre, explicación, propiedades, ejemplos de
consultas, cambios e impacto. No editor JSON ni interruptores técnicos de
filtros. Breve texto pedagógico explica el beneficio: encontrar, comparar,
organizar y consultar clases de cosas con sus propios atributos; no crear tipos
porque sí. Modificar por conversación la propuesta **no** modifica esquema ni
Markdown hasta confirmar. En la primera versión también puede editarse de
forma compatible el **nombre visible, la descripción y las explicaciones** de
tipos/propiedades ya existentes sin cambiar su identificador estable ni el
tipo de valor; renombrar IDs, convertir propiedades, cambiar el tipo canónico
de una nota y retirar/eliminar definiciones requieren migraciones aparte.

**Fuentes de verdad y reutilización efectiva.** El JSON base actual
`config/note-schema.json` (v3), el compositor
`odyssey_apps/schema_extensions.py` para tipos gestionados por Apps,
`odyssey_core/schema_types.py`, el validador `scripts/validate_note_schema.py`,
la proyección de capacidades/consultas de Notes, los hechos
`AtomicFact(request_id, ordinal)`, `PendingReference` **real**,
`PendingWorkRepository` (solo donde el contrato sea adecuado), el gate
`CanonicalMutationGate`/`execute_prepared_property_mutation` de E3,
identidad/referencias, recibos, historial Git y el refresco derivado son
material de partida. No son una plataforma completa de evolución de esquema;
**identificar explícitamente la laguna antes de ampliar cada componente**.
La preparación simultánea de interpretaciones ya tiene precedentes con
`ThreadPoolExecutor`; la serialización/coordinación segura de escrituras queda
en Core/E3. No proponer un servicio, broker, framework de agentes, índice
semántico alternativo ni base de datos nuevos sin necesidad demostrada.

**Registro editable y versión, especialmente crítico.** Hoy
`RuntimeComposition` carga el JSON al arrancar y compone las extensiones de
Apps; `validate_note` exige que `metadata.schema_version ==
schema['schema_version']`. Un cambio ingenuo a `schema_version:4` invalidaría
de golpe notas existentes durante un rellenado progresivo. Para ampliaciones
**compatibles** (nuevo tipo o propiedad opcional), mantener el formato canónico
v3 y separar una **revisión/generación del registro de usuario** del
`schema_version` físico: registrar la propuesta aprobada en estado de Odyssey
versionado, hacer una composición única `base + Apps + usuario` validada sin
colisiones, y publicar un snapshot consistente para la petición, UI, búsquedas
y Writer. No editar por chat el JSON de Git ni mutar en caliente un diccionario
compartido. Validar todas las notas canónicas pertinentes con el esquema
candidato antes de publicar; publicar atómicamente con historial/rollback y
reconstruir/invalidate índices/capacidades afectados. Una modificación
**incompatible** (nuevos campos obligatorios, cambio de tipo de valor,
renombrado/borrado) queda fuera de v0 hasta tener migración específica segura.
La estrategia exacta de hot reload y almacenamiento de revisiones se decide
tras el inventario acotado, **no** se asume que lo actual ya la implementa.
Los tipos gestionados por Calendar/Tasks/Events no reciben autorización de
ciclo de vida por el editor genérico.

**Una confirmación de estructura, dos consecuencias diferenciadas.** El usuario
aprueba **una sola vez** un cambio compatible de esquema y el trabajo
retrospectivo pertinente; esa aprobación permite rellenar datos con evidencia
clara, sin preguntar por cada nota. No implica autorizar automáticamente
**crear nuevas identidades** halladas después. Esas se presentan juntas con
sus fuentes y posibles duplicados para una **confirmación por lote** posterior.
La aprobación de una propuesta queda ligada a su revisión exacta del registro,
actor y alcance: un clic repetido/replay no puede iniciar otra publicación ni
duplicar el trabajo.

**Propiedad nueva (ejemplo: `person.birth_date`).** Escanear todas las notas
canónicas `person` y sus hechos pertinentes; buscar evidencia exacta de valores
(parcial o completa), admitir ausencia/conflicto sin inventar información ni
sobrescribir un valor corregido. Procesar por lotes/paralelo de forma acotada y
preparar candidatos con procedencia: `note_id`, `revision`/hash de fuente,
`request_id:ordinal` cuando exista, y texto original verificado. Escritura
individual E3 con lectura actual de nota, chequeo de colisiones y CAS;
indexación después. La compatibilidad exige que la propiedad recién añadida
sea inicialmente **opcional**; «vacío» no se representa con valor inventado.

**Fechas parciales reutilizables, no formatos ficticios.** Valor de fecha con
componentes conocidos (año, mes, día, con al menos uno presente) y
combinaciones válidas. `{year: 1985}`, `{year: 1985, month: 3}`,
`{month: 3, day: 12}`, una fecha completa o `{day: 12}` son **formas
conceptuales de representar componentes conocidos**, no cinco propiedades ni
valores Markdown ya definidos; nunca completar a `YYYY-MM-DD` inventando datos. Una consulta sobre marzo encuentra valores con mes 3 acreditado;
una edad exacta no se afirma cuando faltan componentes indispensables. La
introducción de este **tipo de valor genérico** exige cambios consistentes en
validación de metadata y planes, codec Markdown, consultas/índices, representación
y Temporal donde sea aplicable. `date` completo existente permanece intacto.
No hace falta implementarlo antes de poder diseñar/crear otras propiedades;
es una prueba posterior especialmente exigente.

**Tipo nuevo (ejemplo: `book`).** No reclasificar ninguna nota: toda nota ya
tiene `type`. Tras publicarlo, un trabajo retrospectivo escanea los hechos
canónicos de **todos** los tipos, filtrando por evidencias del nuevo concepto;
los hechos Odyssey marcados tienen locatores estables, pero el contenido
Markdown anterior o editado manualmente puede carecer de ellos: no ignorarlo
como **evidencia de lectura**, y nunca prometer un relink determinista cuando
no haya una ocurrencia direccionable. La localización/evidencia debe reflejar
explícitamente esa diferencia,
sin categorización especulativa anterior ni dependencia de `PendingReference`.
Pueden ayudar índices ya existentes, pero si no garantizan cobertura la
inspección por lotes debe cubrir el corpus canónico. Un modelo propone
candidatos con identidad, tipo, citas/facts y posibles agrupaciones; Core
deduplica frente al conjunto de entidades ya existentes. No identificar una
mención literal como entidad inequívoca, ni crear nota ni modificar enlaces
hasta confirmar lote y acreditar una identidad segura. Para el relink,
conservar locatores de hecho/ocurrencia, comprobar bytes o hash/revisión y
cambiar solo la mención exacta bajo E3; ante ambigüedad, editar manualmente o
mantener pendiente. **No reemplazos globales de texto.** Las nuevas peticiones
después de publicar el tipo usan el mismo registro de Core/Planner, no un
segundo extractor permanente.

**Seguridad del modelo de consulta.** La experiencia no pregunta si una
propiedad es filtrable, pero **no se registrará una propiedad sin un mecanismo
de consulta definido y probado**. Para valores numéricos/fechas, filtros
específicos; para texto, operadores compatibles; para referencias, resolución
canónica; y para booleanos/u objetos declarados, extender los operadores
necesarios o dejar ese tipo de propiedad fuera del alcance de v0. El asistente
no prometerá funcionalidades de búsqueda aún no implementadas.

**Trabajos en segundo plano y consultas.** Estado duradero mínimo por
`job_id`/revisión del esquema, `actor`, clase de trabajo, cursor/cohorte de
notas, pendientes, completados, omitidos, contradicciones y recibos. Reanudable
tras reinicio/crash, revalidando notas que cambiaron; idempotencia por fuente,
propiedad/tipo y generación. Progreso sencillo en UI, sin bloquear Chat u otros
dominios por trabajo de IA. *Interpretar* distintas notas en paralelo, con
límite ajustado a RAM/tokens y cancelación/reintento acotado; *mutar* siempre
por el gate seguro, evitando carreras de Git/Markdown. El actual
`DerivedIndexRefreshCoordinator.wait_until_clean` tiene barrera global:
para satisfacer las búsquedas no afectadas se precisará delimitar la barrera
por dependencia/generación o mecanismo equivalente, sin prometer que ya está.
Una consulta sobre la propiedad a medio poblar espera a completitud relevante
o avisa explícitamente de resultados provisionales. No confundir «no evaluada»,
«evaluada sin evidencia», «contradicción», «fallo técnico» y «valor escrito».
Preservar evidencias y correcciones humanas.

**Verificación/criterios de aceptación.** Primero prueba offline con vault
sintético: 0/1/muchas notas; tipo/propiedad ya existentes; nombres/sinónimos
solapados; tipos App vetados; referencias repetidas/ambiguas, mención literal
y fuente obsoleta; notas legacy/fecha parcial; doble clic/replay, cambio de
revisión y reinicio a mitad de trabajo; consulta simultánea relacionada/no
relacionada; sin escrituras al quedar sin evidencia; ningún Markdown alterado
fuera del alcance ni pérdida de hechos. Validar iterativamente el prompt real
con `odyssey-llm-stage`, límites de abstención y coste antes de habilitarlo;
revisiones independientes, gate cross-surface completo y Chromium desde la
**app DEV desplegada** con n8n/IA/Core/E3/Markdown/recarga y actor/vault
sintéticos. No tocar PROD ni notas personales durante pruebas. Medir latencia,
RAM y tokens sin optimizar por inercia.

**Orden siguiente (no implementado aún):** (A) arquitectura-challenge e
inventario de permisos, serialización y composición/compatibilidad v3; (B)
propuesta/validación determinista del registro y snapshot publicado en DEV
con contrato de seguridad y tests; (C) conversación/vista previa y confirmación;
(D) backfill opcional de propiedades, duradero y paralelo con E3;
(E) descubrimiento bajo demanda tras crear tipos con propuestas y confirmación
por lote; (F) fecha parcial genérica y prueba `birth_date` si ese sigue siendo
el primer caso que interesa al usuario. Cada corte se acepta con pruebas
reales de interfaz y no se solapa con una refactorización general de E6.

### Primera entrega técnica: registro compatible (24-10-2026, rama de desarrollo)

El módulo interno `odyssey_runtime/user_schema_registry.py` reutiliza
`compose_application_schema`, `scripts/validate_note_schema.py`, las
capacidades de filtros y el modelo Core, **sin introducir una segunda autoridad
para notas**. Ya permite preparar y validar propuestas estructuradas de
`add_type`, `add_property`, `edit_type_text` y
`edit_property_description`. Los campos nuevos nacen **opcionales** y
consultables; los cambios incompatibles y los tipos gestionados por Apps se
rechazan. El esquema físico permanece v3; el registro del usuario tiene una
revisión independiente. La API interna valida conflicto CAS, consentimiento
estructurado de un llamador de confianza, hash de propuesta, `request_id`
no reutilizable, persistencia atómica y recibos de historial. Pruebas sintéticas
verifican compatibilidad de Markdown, concurrencia y reinicio. No modifica
ningún esquema del repositorio ni vault real.

`RuntimeComposition` puede leer el esquema compuesto desde ese registro **solo
si** `ODYSSEY_USER_SCHEMA_ENABLED=1` y `ODYSSEY_DEPLOYMENT_ENV=DEV`;
el valor predeterminado es apagado. Esta es una lectura de snapshot al arrancar,
**no hot reload** ni aceptación de publicación desde Chat/UI. El objeto
`SchemaConfirmation` NO autentica usuarios por sí mismo; el futuro endpoint
actor-bound deberá verificar la sesión, solicitud original y confirmación
real antes de invocar `publish`. Los recibos son evidencia para recuperación,
no implementan todavía una reversión automática de notas ni publicaciones.

**Segundo corte de integración, solo lectura:** `/notes` y el nodo
Notes de n8n aceptan `schema_preview`, que obliga a suministrar la identidad
ya validada del actor/principal y acepta únicamente `change` y
`expected_revision`. Devuelve revisión, hash exacto de propuesta y la tarjeta
del tipo afectado; no expone todas las definiciones ni publica cambios.
Propuestas sin identidad, con flags ocultos, revisión obsoleta o sin soporte de
consulta se rechazan. Las pruebas ejecutan el **código JS real del validador
n8n** y la ruta HTTP Python con actor sintético: gate final **2.097 Python +
202 JavaScript PASS**. La interfaz actual conserva sus botones informativos
sin presentar todavía este preview como editor conversacional completado.

**Hallazgo de integración:** `schema` aparece en múltiples cierres de Core,
Apps, `NotesQueryService`, escritor e índices construidos al arrancar.
Mutar el diccionario en caliente o reemplazar solo `canonical_schema` sería
inconsistente. La siguiente fase requiere **una transición coherente** para
todos los consumidores (o una frontera explícita de reinicio seguro antes de
habilitar publicación), con control de concurrencia, validación del esquema
candidate sobre el vault de prueba y reconstrucción/reutilización justificada
de índices. Nunca habilitar un endpoint de confirmación sin ese contrato.

**Tercer corte: generación coherente por reinicio controlado (source-only).**
La composición carga una revisión exacta del registro, y el servidor conserva
un **lease compartido de sistema operativo durante toda su vida**. La
publicación de otra revisión necesita el mismo lease en exclusiva y se rechaza
con `SCHEMA_RUNTIME_ACTIVE` mientras el servidor funcione. Al arrancar, el
servidor compara la revisión ya compuesta con la revisión duradera y se niega a
servir una composición obsoleta (`SCHEMA_RUNTIME_GENERATION_STALE`). Así todos
los consumidores que capturan el esquema al crear Core/Apps/Writer/Notes e
índices siguen utilizando **la misma generación por proceso**, aprovechando la
recomposición y validación de índices en el arranque. El lock no intenta
reconfigurarlos a medias. Prueba Linux entre procesos y fake `serve()` real
comprueban exclusión durante servicio y reinicio correcto; los recibos futuros
huérfanos tampoco se ignoran silenciosamente.

**Corrección tras revisión independiente (P1/P2):** el validador rechaza
colisiones de identificadores con tipos o restricciones incompatibles **aunque
el campo previo no fuera filtrable** (`calendar_day.date` es la regresión). El
bloqueo comienza **antes** de construir Core o reconstruir índices:
`build_runtime_from_environment` toma un lease **exclusivo durante todo el
bootstrap**; después el servidor toma su lease compartido y comprueba que la
revisión de arranque siga vigente. Ninguna publicación puede coincidir con un
arranque/servicio; no hay escrituras de índices desde una generación obsoleta.
Si el bootstrap falla, libera el lock. Si una publicación gana el intervalo
entre creación y servicio, ese runtime viejo se niega a atender peticiones.
El digest del esquema de `verified_metadata_catalog._from_complete_index`
además impide reutilizar índices de filtros incompatibles. El servicio HTTP también espera a que finalicen los hilos de peticiones
existentes antes de liberar su lease (`daemon_threads=False`,
`block_on_close=True`); una petición lenta no permite colar una revisión nueva
durante el apagado. Se ha verificado con HTTP local real y respuesta retardada.
Este protocolo es intencionalmente conservador: **no implementa** reinicio
transparente.

**Segunda revisión independiente (boot guard):** antes de adquirir el lease
el factory comprueba el entorno de despliegue, flag, raíces DEV del vault,
índices, pendientes, estado y caché, y que ninguna resuelva bajo
`/data/odyssey`. Si el estado DEV todavía no existe, lo crea **solo después**
de pasar la validación. Esto evita cualquier efecto secundario sobre PROD
cuando una configuración DEV es rechazada; pruebas sobre raíces sintéticas
cubren `ODYSSEY_LIGHT_SOURCE_V1` activo/inactivo, un primer arranque y un
estado enlazado por symlink. No se ejecutaron pruebas sobre datos PROD.

**Cuarto corte — confirmación autorizada + reactivación gestionada (25-10-2026,
source-only, por probar en DEV):** `schema_confirm` desde el circuito
Notes/n8n existente recibe un **clic explícito** sobre la propuesta ya
previsualizada: `change`, revisión, hash SHA256 de esa propuesta y
`request_id`, asociado al actor autenticado que n8n inyecta. Una puerta
adicional `ODYSSEY_SCHEMA_CONFIRM_ENABLED=1`, solo con
`ODYSSEY_USER_SCHEMA_ENABLED=1` y entorno `DEV`, impide habilitarlo en un
despliegue accidental. El servidor confirma **«queued»**, guardando una única
petición de activación en el directorio privado versionado (registro
`pending-activation.json`). No cambia de esquema ni de índices en caliente.
Una propuesta distinta, otra identidad, un hash modificado, la revisión vieja
o dos aprobaciones paralelas no pasan el CAS; reintentar el mismo `request_id`
exige además **el mismo cambio y revisión**, incluso después de activarse:
no genera otra publicación ni falsea qué se aprobó. La confirmación calcula
**antes del ACK** el estado publicado exacto y comprueba el límite físico de
tamaño: no acepta una propuesta que dejaría el reinicio inservible.
Ambos requisitos proceden de defectos P1/P2 hallados en la primera revisión
independiente del PR #156 y reparados con regresiones específicas. La
segunda revisión focalizada del commit reparado no señaló regresiones; su
entorno no disponía de pytest, por lo que la evidencia ejecutable es el
gate oficial independiente de esa revisión (**2.123 Python + 204 JS PASS**).

Tras entregar la respuesta HTTP, el runtime inicia **apagado ordenado** por
un hilo distinto: termina nuevas esperas, drena los handlers HTTP activos
(incluidos E3/Git), suelta el lease de generación y sale con código 75.
El `Restart=on-failure` que **ya existe** en la unidad systemd DEV ejecuta un
nuevo proceso; no se añade servicio ni permiso. Durante el próximo bootstrap,
con lock exclusivo, Core valida de nuevo la solicitud, la publica a través
del registro versionado/recibos y reconstruye los índices y todas las
composiciones con esa revisión. Si el proceso cae tras aceptar el clic y antes
del cierre ordenado, ese mismo bootstrap también encuentra la solicitud
persistida. `schema_status` ofrece la revisión actual (sin identificador) o
el estado de **ese** `request_id` solo a su actor: `queued`/`active`.
«active» no equivale a que el posterior rellenado retrospectivo haya
terminado; esa etapa tendrá estados y contadores propios.

**Límites de seguridad y producto:** el servidor debe estar ejecutándose bajo
el supervisor configurado (`Restart=on-failure`); el API está desactivado por
defecto y aún NO hay botón conectado ni la conversación de IA. La validación
actual comprueba la estructura del esquema, filtros compatibles, identidad y
revisión, **no hace todavía un backfill ni un examen completo del corpus
antes del clic**. No se promete cero interrupción: el reinicio puede hacer
que una consulta próxima observe indisponibilidad temporal; el cliente debe
consultar `schema_status` por `request_id` y esperar la generación activa.
Una caída entre el recibo histórico nuevo y el cambio de puntero mantiene
el mecanismo existente de **fallo cerrado** y exige recuperación explícita;
no se debe afirmar recuperación automática de cualquier punto de fallo.
El endpoint de confirmación solo se puede conectar al diálogo visual después
de una prueba real desde la app DEV, con usuario sintético, aceptación
visible y lectura de notas/índices tras recargar. Nunca activar en PROD.

**Quinto corte, interfaz fuente guiada (25-10-2026, NO interfaz final de IA).**
Se incorpora un panel `Modelo de notas` bajo el botón «Crear nuevo tipo» y
«Personalizar tipo», con acceso también por el evento de navegación de Chat.
Formula preguntas sencillas de nombre, finalidad y datos deseados (o añade
una propiedad a un tipo ordinario); el navegador genera un **borrador
explícito** y se lo envía al `schema_preview` autenticado. El backend valida
la propuesta y devuelve una tarjeta visible antes de habilitar el único botón
«Confirmar este cambio». Todos los campos son consultables por construcción;
el usuario no configura `filterable`. Los tipos App-owned no ofrecen editor.
La respuesta de Notas cruza un validador JS por operación que rechaza estados
inesperados, hash ausente, propiedades mal formadas o autoridad adicional.
La confirmación solo se habilita si `schema_status` anuncia un opt-in DEV
explícito; por defecto se muestra la vista previa **sin mutación**. Una
respuesta incierta no se reenvía automáticamente: se conserva el `request_id`
en sesión y se consulta `schema_status`, incluso después de recargar.
Tras una revisión independiente de la UI se identificaron tres P2: un
seguimiento atascado si el POST no llegó al servidor, botones de edición
incorrectos para ciertos tipos de Core y ausencia de nueva propuesta tras
completar. La solución es no interpretar un 400 genérico como ausencia
segura: solo el status autenticado con error acotado
`SCHEMA_ACTIVATION_NOT_FOUND` permite ofrecer **por elección explícita**
«Descartar seguimiento»; fallos de red conservan el identificador. La
capacidad `schema_editable` procede de la propiedad `managed_by`/
`planner_writable` canónica del tipo, no de nombres especiales. Al activarse
un cambio, se ofrece «Preparar otra propuesta». Pruebas HTTP locales y
JS cubren los tres casos; puerta transversal tras reparación
**2.125 Python + 217 JS PASS**. Un
`status=active` actualiza las capacidades/índices de Notas, **no significa
que haya terminado un análisis retrospectivo**. El módulo está registrado en
el inventario/ruta estática real de n8n (evita el fallo de módulo ES ausente).

**No confundir este corte con conversación IA completada:** la guía es
provisional y no interpreta todavía un relato libre, infiere tipos de dato
semánticamente ni valida solapamientos conceptuales mediante un modelo. Un
campo de texto libre se almacena como `string` salvo elección explícita de
número/fecha completa en la vista de propiedad. Se indica en la pantalla de
manera honesta; no se ha habilitado ni desplegado en DEV. Antes de aceptación
final: integrar el prompt y proveedor aprobados con evaluación real de
modelo, reajustar la propuesta desde lenguaje natural, completar el backfill
E3 y descubrir entidades mencionadas solo tras crear un tipo nuevo; después
hacer pruebas reales desde la app DEV, navegación/recarga y readback físico.

**Sexto corte, conversación de modelo de notas — fuente opt-in (25-10-2026).**
Se añade `odyssey_runtime/schema_suggestion.py`, una especialización de
interpretación **sin escritura** que reutiliza la llamada estricta
`OpenAIConversationGateway._complete` (mismo `gpt-6-luna`, reasoning `low`,
`store=False`, SDK con retry 0/timeout 30 s). No añade proveedor, agente ni
servicio propios. Solicita **una sola respuesta JSON cerrada** por mensaje
(≤1.200 caracteres, catálogo consultable ≤18,5 KB, salida ≤1.200 tokens),
con decisión `ADD_TYPE`, `ADD_PROPERTY`, `REUSE`, `CLARIFY` o `ABSTAIN`, cita
exacta de intención original, cita única por atributo deseado, tipo existente
para añadir/reutilizar y una explicación humana. Todas las citas y tipos
reales se validan determinísticamente. Los nuevos nombres se transforman a
identificadores controlados, sin heurísticas de alias ni creación de entidades
canónicas. Solo si pasa toda la evidencia se ejecuta
`UserSchemaRegistry.preview()` por CAS contra la revisión actual, y se
retorna **solo** una propuesta más su hash. Nunca confirmación ni escritura.
Un resultado inválido falla cerrado, sin «best effort» que invente campos.
Las fechas incompletas NO se reinterpretan como fechas completas: el
contrato instruye `CLARIFY` hasta contar con soporte real.

Se añade la ruta autenticada Notes/n8n `schema_suggest(message,
expected_revision)`, cliente JS validado y área «Explícaselo a Odyssey»
en el panel existente. La conversación soporta una aclaración corta anclada
al mensaje anterior; `REUSE`, `CLARIFY` y `ABSTAIN` son de solo lectura.
`PROPOSE` muestra la misma tarjeta de Core y **no hace clic** en el botón
«Confirmar». El botón sigue detrás de su bandera independiente. El nuevo
`ODYSSEY_SCHEMA_ASSISTANT_ENABLED=1` es **DEV-only** y requiere
`ODYSSEY_USER_SCHEMA_ENABLED=1`; por defecto permanece apagado y se rechaza
antes de cualquier acceso al almacenamiento PROD. Una respuesta de modelo
no puede habilitar esas banderas. Los tipos App-owned siguen protegidos.

**Validación V1, V2 y V3 reales NO aprobadas; habilitación BLOQUEADA.**
El informe reproducible está en
[schema-conversation-live-eval-20261025.md](schema-conversation-live-eval-20261025.md):
24 llamadas reales a `gpt-6-luna` low, 17 decisiones esperadas, 5 rechazos
de validador, 2 elecciones semánticas incorrectas, 36.224 tokens. Ninguna
nota fue modificada: hubo registros de esquema temporales y acceso al
proveedor mediante transient systemd con EnvironmentFile protegido.
El antiguo prompt V1 no está aprobado. La V2 revisa la granularidad de tipos
frente a categorías generales y hace que `ADD_PROPERTY` tenga `description`
**de tipo** nula, conservando la descripción de la propiedad. La matriz
original no se retoca; también hay un holdout de 12 casos sin evaluar.
Prompt V2 SHA256 `c0322c9bbaa6fb234c54ab67cdd97f54532fe61280ec10079bd96a9f11ef06c2`.
La V2 se evaluó con el proveedor real y logró **20/24 coincidencias de
operación, no éxitos semánticos certificados**. Quedan cuatro discrepancias,
una de ellas incompatible con el contrato de fechas parciales: detalle en
[schema-conversation-v2-eval-20261025.md](schema-conversation-v2-eval-20261025.md).
La V3 fue evaluada con **40 llamadas reales sintéticas**: 22/24 etiquetas
de regresión, 9/12 holdout, 2/4 repeticiones; **33/40 etiquetas, NO
33 éxitos semánticos**. Persisten dos bloqueos: ISBN inferido sobre el
tipo genérico `document` y exclusión de plantas laborales que no puede
hacerse cumplir con una mera descripción. Informe íntegro en
[schema-conversation-v3-live-eval-20261025.md](schema-conversation-v3-live-eval-20261025.md).
Queda prohibido activar el asistente hasta validar la semántica y probarlo
desde la app usando vault sintético. **La fuente V4 está preparada, pero NO
evaluada con modelo real**: [contrato y matriz nueva](schema-conversation-v4-contract-20261025.md).
El nuevo prompt exige comprobar granularidad/identidad del tipo destino y
aclarar filtros que no pueden ejecutarse por una mera descripción. La vista
previa deja visible el alcance real de `add_property` y la falta de filtros
automáticos en `add_type`. Estas advertencias y pruebas de contrato no
certifican uncertifican una garantía semántica que el validador estructural no posee.
**V4 fue evaluada posteriormente** con otras 40 llamadas reales (16 holdout,
24 regresión): **39/40 etiquetas** con **0 rechazos**, pero tres desajustes
de idioma y preguntas mejorables. Informe detallado en
[schema-conversation-v4-live-eval-20261025.md](schema-conversation-v4-live-eval-20261025.md).
Su hash es `b52def8fca2037d1260aac595b8b10d9fd8db756b254c3c0a7369e26dad5bd2a`.
No activar aún ni convertir un acierto de etiqueta en certificación semántica.
Se ha preparado V5 **solo en fuente** para corregir fidelidad de idioma,
reutilización sin atributos nuevos e hipótesis temporales; ver
[schema-conversation-v5-contract-20261025.md](schema-conversation-v5-contract-20261025.md).
Su prompt tiene hash `c34023593fb021384013e77c862afee580e8dc04795f4b65b46b8ae423bb3ca4`.
**0 llamadas reales V5**, contrato semántico todavía sin validar. Ambas
banderas de activación continúan apagadas. **Actualización posterior:** la
V5 fue evaluada mediante 24 llamadas reales, 22/24 coincidencias de etiqueta,
pero no superó semántica de propiedades/idioma; véase
[schema-conversation-v5-live-eval-20261025.md](schema-conversation-v5-live-eval-20261025.md).
La V6 se ha preparado sin llamadas reales, con reglas generales de atributo
posesivo, recuentos enteros, fecha parcial e idioma y 12 casos nuevos;
[contrato V6](schema-conversation-v6-contract-20261025.md). Continúan las
banderas desactivadas. La puerta transversal de fuente V2 ahora
incluye también `tests/runtime/test_schema_suggestion.py` y pasa
**2.148 Python + 226 JS** tras corregir también el evaluador; antes de añadirlo ese grupo no
estaba cubierto en el gate. Este recuento sigue sin ser puntuación semántica.

**Estado histórico antes de la evaluación real:** el contrato del prompt tiene
matriz versionada `tests/fixtures/schema_suggestion/evaluation_v1.json`
con **24 casos ES/FR/EN**, negaciones, correcciones, tipos existentes,
propiedades, ausencia de intención, fechas parciales y prompt injection.
Prompt SHA256 `229a3f2e2072bb6c20a198ffc38318406218f7a4057b9d7b833898fc358ce085`,
esquema estricto SHA256 `19acba3f55c8b73eaf823a94bd1400e8510de83d1507e7a538ef46b5744ccc50`.
Los tests SDK simulados / HTTP local / navegador DOM son evidencia de
contrato **NO evidencia de comportamiento de GPT real**. No se ha gastado
presupuesto ni realizado ninguna llamada a modelos de producción para este
prompt, que sigue sin un hash/modelo aceptado semánticamente. La puerta transversal del
corte fuente pasa **2.126 Python + 226 JavaScript** (12 grupos), tras corregir tres
hallazgos P2 de auditoría: la vista «Modificar» conserva tipos
`integer`/`date`/`array[string]` existentes y bloquea cambios de nombre
que degradarían esos tipos, pero sí deja quitar explícitamente propiedades
no deseadas sin alterar las restantes; la aclaración envía texto escrito por
el usuario como evidencia, **nunca la pregunta de la IA**. Tres regresiones
JS nuevas demuestran las fronteras; es prueba
funcional/contractual local, no evaluación del comportamiento de GPT. Para desbloquear
el opt-in hay que ejecutar una campaña de validación con modelo real,
presupuesto finito previamente autorizado, publicar outcomes y errores por
caso, corregir y reevaluar fallos semánticos, y completar una aceptación
Chromium→n8n→runtime→estado/aprobación con vault sintético. No desplegar ni
fusionar como feature operativa ni afirmar «IA validada» todavía. El backfill
E3 y el descubrimiento retrospectivo siguen en etapas separadas.

**Pequeña corrección de UI:** la pantalla de Notas deja de mostrar al usuario
el atributo técnico «filtrable» en las descripciones de propiedades y explica
el beneficio real de un tipo nuevo con ejemplos; sus botones permanecen
informativos («Próximamente»), no simulan una operación de IA publicada.

**Nota histórica (previa al sexto corte):** aún no había IA/contrato,
interfaz ni vista previa conectadas. Actualmente sí están en fuente pero
siguen apagadas y semánticamente no aceptadas. Sigue pendiente aceptación
real desde Chromium en DEV, migración de
esquema incompatible, trabajo retrospectivo, descubrimiento de entidades,
confirmación por lotes, fecha parcial o aceptación E2E del navegador en DEV.
No debe presentarse esta entrega de infraestructura como una función utilizable
por el usuario.

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

## D. Human-edited proposals and one final AI review — source-only, after V6

**Product correction from user feedback:** Stop tuning the initial model until
it gets every cosmetic name/property right. The assistant proposes a schema
change; **the user owns the draft**. The Notes editor can now edit the type
name/description and individual property name, description and value type
(`string`, `integer`, `date`, `array[string]`), add or remove properties and
rerun the trusted Core `schema_preview` without another suggestion call. The
editor enforces bounded rows, unique canonical property IDs and supported
value types, and Core validates the full effective schema. There is no hidden
property renaming/type coercion or reclassification of historical notes.

A separate authenticated operation `schema_review` accepts the original user
request (or empty when no assistant was used), **the exact human-edited
change**, expected revision and `proposal_hash`. The service re-runs the
Core preview/CAS and refuses a stale or mismatched hash *before* a bounded
**single read-only** strict-JSON review via the existing conversation gateway.
The reviewer returns only `READY`/`CHECK`, a short explanation and at most
three issues. It cannot return changes, approval, writes, migration plans or
assert that a non-executable description enforces a filter. Material concerns
are advice the user can review/correct or explicitly choose to proceed with;
Core still controls hard schema invariants.

For assistant-generated drafts the **UI requires the final review** of the
current proposal hash before its `Confirmar` button is enabled; editing or
re-preview invalidates the earlier review, and a late/mismatched response
cannot enable confirmation. For manual proposals Core's canonical preview
remains sufficient, with an optional AI review. Confirmation always requires
a separate explicit user click and existing activation flag/receipts; AI
never confirms automatically. The feature remains opt-in/off and this is a
**source-only** implementation, not a claim of deployed app/real-model E2E.
No new background backfill or retrospective discovery is implemented by
this UI change: those post-activation stages remain separate.

**Interacción Chromium local (25-10-2026, fuente `38445eb`):**
`scripts/odyssey_schema_editor_chromium_synthetic.cjs` carga los módulos
reales `schema-model.js` y `notes-client.js` en Chromium arm64, interactúa
mediante clicks/tecleo en 1280×920 y 390×844: propone, entra en edición,
conserva y corrige tipo numérico, elimina/agrega atributos, pide revisión
final y confirma **solo tras la revisión** con el hash actual, una vez por
usuario, sin errores JS ni scroll horizontal en ambos perfiles. Resultado
**PASS/PASS**. Servidor/modelo/recibos **simulados** exclusivamente en
`127.0.0.1`: NO es el DEV desplegado, autenticación n8n, proveedor GPT real,
mutación física ni E2E aceptado. Reutiliza las bibliotecas Chromium ya
cacheadas, sin instalar dependencias del sistema; `odyssey-dev-e2e` sigue
requiriendo app real y vault sintético para la aceptación posterior.

**Comprobación posterior antes de desplegar (25-10-2026, fuente `de2b370`):**
la prueba de Chromium móvil y escritorio se reprodujo **PASS/PASS** con
interacciones visibles `click/type/select` en lugar de escribir valores
mediante `evaluate()` en el DOM. Para lanzarla en Pi se necesitó reusar el
bundle de bibliotecas locales ya auditadas y ajustar `LD_LIBRARY_PATH` **solo
en el proceso de prueba**; no se modificó el sistema operativo.
Las pruebas del runtime autenticado real / revisión final (63 Python) y de
transporte/UI (34 JS) pasaron; la skill `odyssey-skill-steward` superó el
`quick_validate.py` oficial y el docs guard. El test browser-only sigue
usando **proveedor y servicio simulados**, aunque sí ejecuta el módulo JS
real. El navegador sobre el DEV actualmente desplegado en `050f26f` pasó
una regresión **solo de lectura** (17 detalles/17 SVG, recarga, sin errores)
pero no contiene esta funcionalidad.

**Bloqueo actual de adopción:** `python scripts/odyssey_dev_public_routes.py
status --machine` señala `DRIFT`, ya que la configuración pública de
Cloudflare DEV carece de `/api/schema-model.js` presente en el inventario
de rutas de la nueva fuente. Su actualización está expresamente protegida
por `--authorized-dev-change`, una autorización aparte, y **no se ejecutó**
solo con una orden genérica de probar. No ha habido despliegue, cambio de
Cloudflare, llamada GPT, aprobación real, escritura física ni prueba
Chromium→n8n→Core de la nueva funcionalidad. App E2E = **NO VERIFICADO**.

Operational learning: added `.codex/skills/odyssey-skill-steward` and its
minimal always-on routing in `AGENTS.md`, built against the already installed
first-party Codex `skill-creator`. It notices recurrent agent mistakes or
manual patterns **during work**; it first improves an existing skill rather
than creating another for every bug. Skills do not work autonomously between
chats or substitute for code/tests.

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
