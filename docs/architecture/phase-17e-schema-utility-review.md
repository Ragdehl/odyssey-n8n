# Phase 17E schema utility review

Status: **IN PROGRESS**

This document is the working decision record for the Phase 17E pre-E2E schema utility review defined in the canonical Functional Roadmap and governed by the Odyssey knowledge-model direction.

The review classifies each current canonical type and property as `KEEP`, `DEFER`, or `REMOVE` based primarily on direct user-visible value. No ontology/schema change is implied by documenting a review decision; actual schema changes still require explicit proposal, validation, and human approval.

## Review test

For each note type and property, ask separately:

```text
NOTE VALUE
Why does this thing deserve a stable note identity?

TYPE VALUE
What recurring user-visible behavior becomes possible because Odyssey knows what kind of thing it is?

PROPERTY VALUE
What deterministic filter, sort, comparison, calculation, reminder, automation, or application behavior becomes possible because the value is structured?
```

Structure is not justified merely because it saves LLM tokens or is easy to model.

## Schema ownership boundary

Odyssey Core owns the **mechanism** for registered schema, not the product meaning of every domain type.

```text
Odyssey Core
    |
    +--> registry / validation
    +--> safe create/update/delete
    +--> retrieval / links / history
    |
    `--> registered schema values
            |
            +--> Core-owned generic types
            +--> app/domain-owned types and properties
            `--> future explicit user-defined extensions
```

A domain application owns the semantics and user-facing behavior of the types/properties it contributes. Core should be able to validate, store, retrieve, mutate, link, and audit those values without implementing the application's business workflow.

Therefore Phase 17E should not force every current type to remain permanently Core-owned merely because it currently lives in the single canonical `note-schema.json`. Until a safe extension/registration mechanism exists, useful domain types may remain in the current registry as an implementation bridge.

When an application later proposes a type/property, the extension boundary should detect overlap with existing registered schema and prefer reuse when the proposed structure represents the same fundamental entity class. Roles or app-specific states should normally be properties rather than duplicate types. True new entity classes may be registered as domain-owned types through the future validated extension contract.

Detailed domain properties should generally be decided when the corresponding application is designed, rather than pre-modelled now. Phase 17E only needs to preserve clear ownership and avoid prematurely expanding Core ontology.

## Type decisions

### `concept` — KEEP

**Ownership:** Core-owned generic type.

**Note value:** an abstract subject with stable identity can accumulate knowledge and links across contexts.

**Type value:** allows concept-only collections/retrieval and distinguishes abstract reusable subjects from projects, people, documents, tasks, and other entity classes.

**Type-specific properties:** none. Keep none for now; no concrete concept property currently unlocks enough user-facing behavior to justify extra schema.

**Risk to retain in validation:** `concept` must not become the planner's generic fallback whenever another type is uncertain. Existing planner benchmarks have exercised type discrimination; Phase 17E retrieval/planner validation should continue to include sentinel cases for overuse of `concept`.

### `project` — KEEP

**Ownership:** domain-owned in the future Projects/Tasks application; retained in the current registry until the extension boundary exists.

**Note value:** a project deserves persistent identity because decisions, ideas, tasks, documents, facts, and links can accumulate around the same initiative over time.

**Type value:** enables project-only views/retrieval and a stable project identity that later project-oriented applications or workflows can target.

**Type-specific properties:** none now. Project-specific fields such as `status`, `deadline`, `priority`, `owner`, or `progress` should be defined by the Projects/Tasks domain when that application is designed, then registered through Odyssey's schema boundary rather than becoming ad hoc frontmatter.

### `task` — KEEP

**Ownership:** domain-owned in the future Projects/Tasks application; retained in the current registry until the extension boundary exists.

**Note value:** an actionable item can deserve persistent identity when context, facts, documents, projects, dependencies, and later updates accumulate around the same action.

**Type value:** distinguishes actionable knowledge from ordinary facts/concepts and enables task-only views, retrieval, and later task application behavior.

**Type-specific properties:** none now. Expected future domain properties such as `status`, `due_date`, project membership, or parent/subtask relations should be designed with the Projects/Tasks application. Odyssey Core should supply the generic validated property/reference mechanism rather than owning task workflow semantics.

**Future schema capability to revisit:** relationships such as `project: [[Odyssey]]` or `parent_task: [[Another task]]` suggest a future typed entity-reference property contract. Do not add that contract during this review without the application use case and extension design.

### `store` — KEEP

**Ownership:** domain-owned in a future Purchases application; retained in the current registry until the extension boundary exists.

**Note value:** a physical or virtual store has reusable identity across many purchases and can accumulate facts or links over time.

**Type value:** enables store-only collections/retrieval and gives a purchases application a stable identity for where purchases occurred.

**Type-specific properties:** none now. Store-specific structure such as address, chain, online/offline state, or other commerce fields should be defined only when the Purchases application demonstrates a concrete user-facing need.

### `product` — KEEP

**Ownership:** domain-owned in a future Purchases/commerce application; retained in the current registry until the extension boundary exists.

**Note value:** a product has reusable identity across repeated purchases and other contexts, allowing facts and purchase history to accumulate around the same thing rather than creating a new entity for every occurrence.

**Type value:** lets commerce-oriented applications distinguish products from general concepts and supports product-only retrieval, recurrence, comparison, and later purchase analysis.

**Type-specific properties:** none now. Fields such as brand, barcode, category, or other commerce structure should be designed only when the application proves the user-facing need. Transaction-specific values such as a paid price should not automatically become product properties when they naturally belong to a purchase occurrence.

### `purchase` — KEEP

**Ownership:** domain-owned in a future Purchases application; retained in the current registry until the extension boundary exists.

**Note value:** a concrete purchase occurrence can deserve stable identity because products, store, documents, prices, totals, and later questions can all refer back to the same transaction.

**Type value:** distinguishes the transaction/occurrence from reusable product and store identities and enables purchase-specific retrieval and later analytics.

**Type-specific properties:** none now. Transaction structure such as store, purchase date, total, currency, and line items should be designed with the Purchases application.

**Boundary to preserve:** a purchase is the transaction/occurrence; a receipt or ticket is a document that may evidence that purchase. Do not collapse the two concepts automatically.

### `recipe` — KEEP

**Ownership:** domain-owned in a future Recipes/cooking application; retained in the current registry until the extension boundary exists.

**Note value:** a recipe is reusable knowledge with stable identity that can accumulate ingredients, preparation, variations, comments, and links over time.

**Type value:** enables recipe-only retrieval and lets a cooking application distinguish a recipe from products/ingredients or ordinary concepts.

**Type-specific properties:** none now. Structure such as servings, preparation time, ingredients, cooking time, or freezer suitability should be designed only when the cooking application demonstrates the concrete behavior it needs.

### `document` — KEEP

**Ownership:** Core-owned generic type.

**Note value:** a document or document-like artifact can have stable identity independent from the physical PDF/DOCX/image and can accumulate facts, links, provenance, and later questions around that same artifact.

**Type value:** documents occur across many domains and applications, so Core benefits from distinguishing document identities from concepts, people, tasks, projects, or domain transactions.

**Type-specific properties:** none now. Possible fields such as document date, issuer, file path, MIME type, expiry date, or document subtype should be introduced only when real cross-domain or app behavior justifies them.

**Boundary to preserve:** the canonical Markdown note represents knowledge about the document; it does not require the source file itself to be embedded in that note.

### `person` — KEEP

**Ownership:** Core-owned generic type.

**Note value:** a person has reusable identity across essentially every domain and can accumulate facts and relationships over time.

**Type value:** lets Core resolve and retrieve people as stable entities independent from any particular contacts, family, project, or business application.

**Current type-specific properties:** defer them from the minimal Core contract:

- `birth_date` — **DEFER from Core**. Useful structured knowledge, but its concrete behavior belongs naturally to future People/Contacts/Family capabilities unless cross-domain evidence later justifies making it universal.
- `relationship_to_user` — **DEFER from Core**. A relationship can remain ordinary knowledge initially; future people/family or multi-user semantics may require a richer relationship model than one user-relative string.

The type remains Core-owned even if these current properties move to a later domain extension.

### `journal_entry` — KEEP

**Ownership:** domain-owned in a future Journaling/capture application; retained in the current registry until the extension boundary exists.

**Note value:** a journal entry represents a personal experience, reflection, or occurrence situated in time when there may be no stable external entity that should own the knowledge. A present-tense personal reflection such as `Hoy estoy pensando si cambiar el sofá` may legitimately be journal knowledge when the thing being preserved is the user's lived reflection at that moment.

**Type value:** enables diary/time-oriented retrieval without forcing personal experiences or reflections into `concept` merely because they lack another entity class.

**`entry_date`: KEEP with the Journaling domain.** It is semantically central to the entry because it records the date the journal content refers to, which may differ from Odyssey's `created_at` lifecycle timestamp. The domain should own that property together with the type.

### Type review summary

```text
CORE-OWNED GENERIC TYPES
├─ concept
├─ document
└─ person

DOMAIN / APP-OWNED TYPES
├─ project       -> Projects/Tasks
├─ task          -> Projects/Tasks
├─ store         -> Purchases
├─ product       -> Purchases/commerce
├─ purchase      -> Purchases
├─ recipe        -> Recipes/cooking
└─ journal_entry -> Journaling
```

All current types remain `KEEP` as useful registered types for now. The important Phase 17E change is ownership: not every useful type belongs permanently to Core. Domain-owned types remain in the single current registry only as an implementation bridge until a safe schema-extension/registration boundary exists.

## Type composition decision

### Multiple simultaneous canonical types — DEFER

Keep the current simple model:

```text
one canonical note
    |
    +--> one primary `type`
    |
    +--> no `subtype` in the active Core schema (deferred until a true stable specialization)
    |
    +--> properties for structured roles/relationships/state when they unlock user behavior
    |
    `--> tags/facts for cross-cutting or ordinary knowledge
```

Do **not** change `type` into an array or introduce multiple simultaneous canonical types now.

The primary type answers:

> What fundamental kind of entity is this?

Subtype remains deferred. If later activated, it should represent a genuine specialization of that parent type, for example a possible future `document -> invoice` relationship when the specialization unlocks useful behavior. The current canonical schema does not reserve or expose a `subtype` field.

Roles or relationships should not be modeled as additional types when an existing structured property expresses them more directly. For example, a child remains `type: person`; if the relationship to the user matters for recurring filtering or behavior, a future relationship property/contract is more appropriate than a second `child` type.

Reconsider multi-type notes only after a concrete case demonstrates that **one stable identity genuinely needs the independent user-facing capabilities/property contracts of two canonical types at the same time**. At that point, evaluate composition conflicts explicitly, including required properties, incompatible type combinations, property-name collisions, migration semantics, and planner/retrieval complexity.

This keeps Odyssey from introducing ontology composition machinery before there is evidence that it solves a real user problem.

## Application composition direction

Future Odyssey applications should be independently useful products, but they should not be forced to reimplement generic capabilities already provided by another reusable application/capability.

Prefer explicit composition when it produces real reuse:

```text
Reminder capability
        ^
        |
     Tasks app
        ^
        |
   Projects app
```

For example, a Tasks application may depend on a reusable reminder capability rather than implement reminders itself, and a Projects application may reuse Tasks rather than invent a second incompatible task system. Installation of a higher-level application may later install or activate its declared dependencies automatically.

Do not implement a general package/plugin manager now. The first real applications should define the smallest dependency contract from evidence. A future dependency mechanism should at least make dependencies explicit, prevent circular dependency graphs, keep Odyssey Core as the shared safe knowledge boundary, and avoid applications bypassing Core to mutate canonical notes independently.

The goal is **Lego-like composition of reusable capabilities**, not a monolith and not a collection of isolated applications that duplicate the same behavior differently.

## Shared knowledge / household use case

Multi-user sharing has a concrete personal-product use case worth preserving: **shared household knowledge that both users can update and see promptly**, such as a common shopping list.

Example:

```text
user A: "falta queso y cereales"
             |
             v
      shared knowledge/list
             |
             v
user B sees the updated list when shopping
```

This is more useful as a design target than abstract multi-user support because it exercises real requirements: stable shared identity, read/write authorization, synchronization or event propagation, conflict handling, and a clear distinction between private and shared knowledge.

Do not implement sharing during Phase 17E. When multi-user work becomes justified, use shared household notes/lists as an early validation scenario and design authentication, authorization, storage/synchronization boundaries, and concurrent-write behavior before claiming real privacy or collaboration semantics.

## Product-family naming direction

Future applications built on Odyssey should have independent product identities while clearly belonging to the same family. Prefer names from *The Odyssey* or closely related Greek mythology **only when the mythological role meaningfully matches the application's function**.

The name `Odyssey` should have a conceptual relationship with Homer's poem rather than being a decorative Greek reference. The useful metaphor is that the product accumulates experiences, people, places, decisions, and knowledge over time, preserves their identity and history, and helps the user navigate back to what matters later.

A concise product definition to preserve is:

> **Odyssey is a persistent knowledge layer that turns fragments accumulated through life and work into connected, durable knowledge that humans, applications, and AI agents can safely return to and use.**

Possible future naming directions, to be decided only when each application's real scope is known:

```text
Projects / tasks      -> Athena
                         strategy, guidance, planning, helping Odysseus act

Messaging / mail /
translation           -> Hermes
                         messenger, movement of information, crossing boundaries

Home / property       -> Ithaca
                         home, destination, return

Recipes / food        -> Circe or another food/hospitality-related name
                         candidate only; decide from the real application scope

Time / scheduling     -> Chronos
                         only if the application is fundamentally about time;
                         avoid confusing Chronos (time) with Cronus/Kronos (Titan)
```

These are candidates, not reserved names. The naming family must not imply a monolithic Odyssey UI: applications may be independently developed while depending on Odyssey as the persistent knowledge layer.

## Next review target

Common metadata fields (`id`, `name`, `type`, lifecycle metadata, aliases, tags); `subtype` is deferred and absent.
