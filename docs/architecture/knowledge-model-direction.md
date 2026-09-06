# Odyssey Knowledge Model

Status: **adopted current architecture**.

This document is the canonical prose owner for how Odyssey represents personal knowledge. Exact machine schema lives in [`config/note-schema.json`](../../config/note-schema.json); phase documents and benchmarks preserve the evidence that led here.

## One stable note identity, atomic knowledge inside it

Odyssey normally keeps one canonical Markdown note per logical entity or knowledge object rather than one file per fact.

```text
canonical entity note
      |
      +--> stable technical identity
      +--> sparse structured metadata/state
      +--> human-readable links/content
      `--> append-first atomic facts
```

Physical fragmentation into one file per fact would make identity, Obsidian navigation, properties, links, and application access unnecessarily complex. Atomicity is logical inside the entity note.

Each Odyssey-created atomic fact is a one-line Markdown list item followed by a hidden request-derived marker. The current implementation derives a note-scoped locator from `request_id + ordinal`; globally the containing stable note ID disambiguates it.

Conceptually:

```markdown
# Added 29-08-2026
- Marta trabaja en [[Thales]].
  <!-- odyssey:fact request=R123 ordinal=0 -->
```

The exact parser/renderer contract lives in `odyssey_core/atomic_facts.py`. Do not invent another unrelated fact UUID unless a demonstrated requirement cannot use the existing identity.

## Append-first accumulation

Ordinary new true knowledge normally appends instead of rewriting previous knowledge simply because both facts concern the same subject.

```text
Marta
  2025 -> trabajaba en Airbus
  2026 -> ahora trabaja en Thales
```

Both facts can remain useful. A later true transition does not make an earlier true fact false.

The small semantic mutation vocabulary is:

- **ADD** — ordinary new knowledge;
- **NO_CHANGE** — exact/clearly redundant knowledge;
- **CORRECT** — explicitly false/mistaken prior knowledge must be targeted safely;
- **REMOVE** — explicit deletion authority for the targeted fact/knowledge.

Append-first does not mean append-always. Explicit correction/removal may target prior knowledge. Git history remains audit/recovery evidence; canonical knowledge should not intentionally retain information established as false merely for history.

## Capture chronology is not event time

Atomic facts expose useful human capture chronology through the capture-date heading. That date means when Odyssey recorded the knowledge, not necessarily when the described event happened.

```text
captured_at != happened_at
```

If the user says `Marta empezó en Thales en marzo`, `en marzo` belongs to the knowledge itself. Odyssey must not replace it with the request date.

Do not add redundant universal per-fact timestamps merely for convenience when capture provenance can be recovered through the established request/Git path. Optional future capture context such as location is a separate provenance concern; see [Future capture-context provenance](future-capture-context-provenance.md).

## Identity before creation

Creating another note is not the fallback for uncertain resolution.

```text
reference
  |
  v
resolve existing identity
  |
  +--> one safe identity -> reuse/enrich
  +--> ambiguous --------> fail closed / clarify / pending evidence
  `--> unresolved + explicit creation authority -> create
```

Names, aliases, structured constraints, semantic candidates, and bounded contextual reasoning may contribute evidence. Similarity alone is never identity authority. Stable IDs are independent from current display names and filenames.

## Relationships default to ordinary wikilinks

Odyssey uses ordinary Obsidian `[[wikilinks]]` by default. Linked notes already carry stable identity and type; a generic typed-edge ontology is not required merely to express association.

Introduce a structured relationship/property only when a deterministic user-facing capability needs its semantic role explicitly—for example filtering, calculation, authorization, application logic, or another repeated machine behavior.

Do not duplicate every wikilink as a generic `related_to`/inverse relation pair.

## Types and properties must unlock user value

The test for structure is:

> What can the user repeatedly see, do, filter, compare, calculate, automate, or interact with because this structure exists?

Useful examples include task deadlines/status, purchase totals, house price/surface, or other values used by a concrete application. Ordinary descriptive knowledge should remain a fact when structure adds no useful deterministic capability.

```text
Can this be structured?              <- insufficient reason
What useful capability does it add?  <- governing question
```

The exact active registry and field definitions live only in `config/note-schema.json`. Domain/application types may remain registered centrally today as an implementation bridge; future applications should own their domain semantics through an explicit validated extension boundary rather than expanding Core business logic.

## Tags are explicit free-form facets

`tags` are a generic Core storage/filter/mutation mechanism, not a Core-owned vocabulary. Values are explicitly chosen by the user or application. Core does not define semantic tag IDs, infer them from ordinary wording, or assign hidden lifecycle/security meaning to them.

A tag is not a note type, identity evidence, precise structured property, or replacement for a wikilink.

## Schema evolution is explicit

LLMs, clients, and applications must not silently invent canonical fields or types. Future schema evolution may be conversational, but applying a proposal requires explicit authority and deterministic validation/migration behavior.

Repeated usage can justify a proposal when structure would unlock a real benefit. Retrospective promotion may require safe identity-aware backfill/relinking; never perform broad blind text replacement over the vault.

See [Future pending-reference evolution](future-pending-reference-evolution.md) and [Odyssey Platform Direction](odyssey-platform-direction.md).

## Retrieval representation is derived

The physical source of truth and the best retrieval unit need not be identical. Whole-note, fact-level, or combined projections may be benchmarked as rebuildable indexes while canonical Markdown remains unchanged.

No retrieval optimization gains write authority. A successful fact-level or candidate-reduction benchmark may change evidence selection only after its own adoption gate. The next preserved experiments live in [Future retrieval refinements](future-query-decomposed-retrieval.md).

## Direct user edits are a future ingestion boundary

Odyssey expects that users may eventually edit canonical Markdown directly through Obsidian/filesystem tools. A later ingestion contract should detect external changes without self-trigger loops, inspect/validate only what canonical contracts require, refresh derived state, and audit accepted changes through the normal request/history boundary.

Direct-edit support must not weaken the source-of-truth rule or silently normalize user prose unnecessarily.

## Core invariants

1. Personal knowledge stays human-readable and user-owned.
2. Stable identity survives rename/type-safe lifecycle changes.
3. New true knowledge normally appends; false/removed knowledge may be targeted explicitly.
4. Structure is sparse and capability-driven.
5. Wikilinks are the default relationship mechanism.
6. Ambiguity fails closed.
7. Derived indexes/embeddings never become canonical knowledge or mutation authority.
8. Schema growth is explicit and reviewed.

Historical rationale is preserved primarily in [Phase 17D temporal/atomic semantics](phase-17d-temporal-update-semantics.md), the [Phase 17E schema utility review](phase-17e-schema-utility-review.md), and related tests/benchmarks.
