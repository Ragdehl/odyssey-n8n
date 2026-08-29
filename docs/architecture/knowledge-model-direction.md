# Odyssey knowledge-model direction

Status: **product/architecture direction to validate before the first real E2E; not yet a production implementation contract**

## Purpose

Preserve the emerging Odyssey knowledge-model principles discovered while refining temporal updates, schema evolution, and retrieval. The goal is to simplify the product rather than turn every piece of knowledge into schema or every update into free-form Markdown surgery.

The intended product direction is:

```text
one canonical Markdown note per entity
                |
                +--> sparse structured state when it unlocks user-visible behavior
                |
                `--> append-first atomic facts for ordinary knowledge
```

This keeps stable entity identity, Markdown ownership, Obsidian interoperability, wikilinks, request-level Git history, and rebuildable indexes while making ordinary knowledge accumulation safer and easier to reason about.

## 1. One entity note, atomic facts inside it

Do **not** move to one Markdown file per fact merely to gain atomicity. Physical fragmentation would make entity reconstruction, wikilinks, current properties, Obsidian use, and application access substantially more complex.

Instead, keep one canonical entity note and make its human-readable knowledge logically atomic inside the body.

Conceptually:

```text
Marta.md
  |
  +--> fact from request R1
  +--> fact from request R2
  +--> fact from request R3
  `--> fact from request R4
```

A single request may create several facts, so `request_id` alone is not a unique fact locator. Avoid another independent UUID unless evidence requires one. A minimal derived locator such as `request_id + ordinal` is sufficient when a specific fact must later be addressed.

Example:

```text
request R123
  +--> R123:0  works at Thales
  +--> R123:1  has two children
  `--> R123:2  plans to move to Lyon
```

This locator is machine-facing; it need not clutter the normal human view.

## 2. Append-first knowledge accumulation

Ordinary new knowledge should normally be appended rather than used to rewrite an older statement merely because the two statements concern the same subject.

Example:

```markdown
# Marta

## Añadido el 12 de marzo de 2026

- Trabaja en [[Airbus]].

## Añadido el 29 de agosto de 2026

- Ahora trabaja en [[Thales]].
```

Odyssey does not need to classify the Airbus fact as `historical` merely to preserve it. The chronology and language already provide meaningful context. A real-world transition can often be represented simply as additional knowledge.

The initial mutation vocabulary should remain small:

```text
ADD        ordinary new knowledge
NO_CHANGE  exact/clearly redundant knowledge
CORRECT    explicit false/mistaken prior knowledge
REMOVE     explicit deletion authority
```

Do not introduce event sourcing, universal temporal states, or history arrays merely to encode normal evolution.

### Corrections and removals remain special

Append-first does not mean append-always.

If the user explicitly establishes that stored knowledge is false or asks to remove it, Odyssey must be able to address the relevant prior fact safely and correct/remove it. Git history remains the audit/recovery record; canonical knowledge should not intentionally retain a fact known to be false merely for provenance.

Exact or sufficiently deterministic duplicate detection should prevent repeated identical facts from accumulating unnecessarily.

## 3. Human-visible capture chronology without redundant fact metadata

The user should be able to read a note and understand that knowledge was captured at different moments.

Prefer a visible grouping such as:

```markdown
## Añadido el 29 de agosto de 2026
```

rather than displaying machine provenance on every line.

This visible date means **when Odyssey received/recorded the knowledge**, not necessarily when the described real-world event happened.

```text
recorded/captured time != domain/event time
```

If the user says `Marta empezó en Thales en marzo`, the fact should preserve `en marzo`; Odyssey must not infer that the transition happened on the request date.

Do not duplicate a separate `recorded_at` field on every fact merely because the UI shows a capture date if that date can be reconstructed reliably from the request/Git provenance. The exact durable representation should be chosen during implementation, but avoid redundant metadata without a concrete need.

Do not store the Git commit SHA inside each fact: the commit does not exist until after the Markdown change. Reuse the already-established request correlation instead:

```text
fact locator -> request_id -> Git commit trailer -> commit/date
```

## 4. Types and properties must unlock direct user value

Types and properties are **not justified merely because they reduce model tokens or make Odyssey's internal retrieval easier**.

The user-facing test is:

> What can the user now repeatedly see, do, filter, compare, calculate, automate, or interact with because this structure exists?

A type should exist when treating entities as that kind of thing unlocks a useful recurring behavior or view.

Examples:

```text
type: task
  -> pending/completed views
  -> deadlines
  -> reminders

type: house
  -> house collection
  -> map
  -> comparisons
  -> visit workflow

type: purchase
  -> spending totals
  -> stores/products
  -> reports
```

A property should exist when a value needs deterministic behavior such as filtering, sorting, calculation, comparison, reminders, application logic, or another user-visible capability.

Examples:

```text
due_date
price
surface
status
purchase_total
```

Conversely, ordinary knowledge should remain a fact when structure would add no meaningful user capability.

The governing question is **not**:

```text
Can this be structured?
```

It is:

```text
What useful user capability does structuring this unlock?
```

If the only answer is `Odyssey may spend fewer tokens`, that is not sufficient product justification by itself.

## 5. Emergent schema should be proposed from repeated use

Most users should not arrive knowing that they want to create a type or property. Odyssey can instead observe recurring knowledge patterns and propose structure when it would unlock an identifiable benefit.

Example:

```text
many recurring house-like entities
        +
repeated concepts such as price / surface / location
        +
a concrete useful capability such as comparison/map/filtering
        |
        v
schema candidate
        |
        v
user-facing proposal explaining the benefit
        |
        v
explicit approval
        |
        v
validated schema change
```

The proposal should be phrased in product terms, not ontology terms. Prefer:

> You keep information about many houses. If Odyssey treats them as a collection, you could compare them by price, surface, or area. Do you want that?

rather than:

> Create type `house` with properties `price` and `surface`?

An LLM may propose structure but must never silently mutate the canonical schema. The existing schema-coach direction remains applicable: inspect overlap/collisions, ask only necessary questions, require explicit approval, and apply deterministic validation/migration.

## 6. Retrospective promotion requires safe backfill and relinking

Emergent schema creates a real migration problem that must be preserved explicitly.

Before `house` exists, Odyssey may have facts such as:

```text
- Visitamos la casa de Balma y nos gustó el jardín.
- La casa de Balma costaba 385.000 euros.
```

If the user later approves `house` and `Casa de Balma` becomes a canonical entity, Odyssey should be able to promote relevant prior knowledge and create safe wikilinks back to that identity:

```markdown
- Visitamos [[Casa de Balma]] y nos gustó el jardín.
- [[Casa de Balma]] costaba 385.000 euros.
```

This is not merely schema backfill; it is **identity + reference backfill**.

The migration must therefore:

1. discover historical facts that plausibly refer to the newly promoted entity/type;
2. resolve identity with the same fail-closed rules as ordinary Odyssey references;
3. rewrite only references that are safely attributable;
4. preserve original knowledge wording as much as possible;
5. leave ambiguous mentions unresolved/pending rather than creating false links;
6. rebuild derived indexes after canonical Markdown changes.

Do not perform broad blind text replacement over the vault. Reuse stable identity, reference-binding, pending-work, request-level execution, and Git history boundaries where possible.

A future schema extension may also derive new structured property values from existing facts, but the source facts should remain canonical knowledge unless they are explicitly known to be false/redundant under a separate contract.

## 7. Fact-level embeddings are a retrieval hypothesis, not an established conclusion

Odyssey already uses local multilingual MiniLM embeddings (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`) to retrieve broad semantic candidates before stronger reasoning.

Existing 1,000-note evidence showed a recall-first profile approximately like:

```text
Top 5    72%
Top 20   80%
Top 50   88%
Top 100  100%
```

so MiniLM has been useful for broad reduction but not sufficient for aggressive safe narrowing by itself.

Odyssey has also already tested fragment-level similarity in a different context. An adversarial writing benchmark split notes into:

- whole-note representations;
- per-unit fragments;
- two-unit blocks.

Fragment-level similarity could improve semantic scores substantially in some overlap cases, but **no cosine threshold safely separated UPDATE/overlap from independent APPEND facts**. Therefore fragment MiniLM evidence was explicitly not safe as autonomous write authority.

That result must not be forgotten or misapplied.

However, the new atomic-fact model creates a different retrieval hypothesis:

```text
physical source of truth: one entity Markdown note
retrieval unit: individual atomic fact
```

This may reduce semantic dilution in long heterogeneous notes and reduce the context sent to Luna/Sol, but it is **not yet proven**.

Before changing production retrieval, benchmark at least:

```text
whole-note MiniLM
vs
fact-level MiniLM
vs
combined entity + fact retrieval
```

Measure:

- recall of the correct entity/fact;
- recall at practical Top-K values;
- long-note versus short-note behavior;
- contextual identity cases;
- Spanish/French cases;
- number of candidates and tokens eventually sent to stronger models;
- latency and local resource cost.

Do not use a successful fact-level retrieval benchmark to authorize writes automatically. Retrieval evidence and mutation authority remain separate concerns.

## 8. Pre-E2E schema utility review

Before treating the initial schema as product-ready, perform a dedicated review of every current type and property.

For each one, classify:

```text
KEEP    demonstrated/direct user capability
DEFER   plausible future capability but not justified now
REMOVE  structure with no sufficient user-facing value
```

Ask for every type/property:

1. What direct user-visible view, action, filter, comparison, calculation, automation, or behavior does it unlock?
2. Could the information remain an ordinary fact without losing that capability?
3. Is it being kept merely to make retrieval cheaper?
4. Would an application/domain pack own it more naturally than Odyssey Core?

This review should also define how emergent schema candidates are surfaced later without forcing users to understand schema design.

## 9. Manual user edits remain a later ingestion boundary

Direct Obsidian/filesystem edits are expected and should eventually be treated as another authorized source of knowledge rather than as malformed Odyssey output.

A later contract should define:

```text
external file change
      -> detect outside Odyssey's own write loop
      -> inspect diff
      -> ingest/validate new or corrected knowledge
      -> normalize only what is necessary
      -> rebuild derived state
      -> commit/audit through the normal request boundary
```

Git is useful for audit/diff history but does not itself provide the always-on filesystem trigger. Avoid self-trigger loops by distinguishing Odyssey-originated writes from external edits.

This remains later hardening work; do not block the atomic-fact knowledge model on it.

## Product principle

The intended differentiator is not maximum schema configurability. It is:

> **Odyssey accumulates knowledge freely, and introduces structure only when that structure unlocks something the user actually wants to do.**

Facts are the memory. Types and properties are optional product capabilities layered on top when they earn their complexity.
