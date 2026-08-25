# Phase 16 reference binding and pre-writer wikilinks

## Purpose

This document is the canonical contract for materializing semantic `KnowledgeUnit.references` into ordinary Markdown `[[wikilinks]]` during Phase 16.

Phase 15 already preserves logical references between knowledge units, but the current `KnowledgeReference(target_index, role)` shape does not itself identify a stable repository note or a text span that can safely be rewritten after a semantic writer has changed the body. Phase 16 must therefore bind references **before** the CREATE/UPDATE writer sees the facts that contain them.

The goal is to keep reference placement deterministic and avoid a second LLM call or post-hoc text guessing.

## Core ordering decision

Reference materialization happens before semantic body writing:

```text
validated WriteAction / KnowledgeUnit(s)
        |
        v
preserve reference occurrence in the planned fact
        |
        v
resolve/authorize every referenced target
        |
        +--> existing target -> stable resolved identity
        |
        +--> same-request CREATE -> authorize CREATE, then allocate identity/path
        |
        `--> ambiguous/unresolved -> no wikilink; preserve pending reference
        |
        v
Core materializes safe references as [[wikilinks]]
        |
        v
Luna receives facts with wikilinks already present
        |
        v
bounded CREATE/UPDATE body operation
        |
        v
Core validates and persists
```

Do **not** ask a later LLM to rediscover which words in writer output represented a reference. Do **not** apply a blind string replacement after Luna has rewritten or reorganized the sentence.

## Reference occurrence contract

The current `KnowledgeReference` records which knowledge unit is referenced and the semantic role, but not where that reference occurs inside a fact. That is insufficient for deterministic pre-writer wikilink insertion.

Before implementing reference materialization, refine the planning/materialization contract so each reference occurrence is bound to the fact text deterministically. A planner-emitted placeholder/token or an equivalent closed structured representation is acceptable; the exact representation must be chosen during the Phase 16 reference-binding implementation and validated locally.

Conceptually:

```text
fact:
  "Compré {{ref:1}} en {{ref:0}}."

references:
  ref:0 -> unit 0, role=store
  ref:1 -> unit 1, role=product
```

After safe identity binding:

```text
"Compré [[Leche Pascual]] en [[Carrefour Balma]]."
```

The placeholder syntax above is illustrative, not yet a frozen public schema. The invariant is that **reference placement is decided before the writer and can be materialized by Core without semantic inference**.

The actual Obsidian link target must be derived deterministically from the authoritative existing path or the preallocated CREATE path, with an optional display label when needed. A primary name or alias alone is never sufficient evidence for the physical link target when it could be ambiguous.

## Existing referenced notes

When a reference points to knowledge that already exists, reuse the existing Phase 9-11 identity stack. The planner does not choose the repository note; Core binds the reference only after one safe stable identity has been resolved.

If several existing notes remain plausible, or identity otherwise remains ambiguous, Phase 16 must not guess and must not create a wikilink.

For the current non-HITL system:

```text
unique safe target    -> materialize [[wikilink]]
ambiguous target      -> keep human-readable text unlinked
unresolved target     -> keep human-readable text unlinked unless CREATE is independently authorized
```

An ambiguous or unresolved reference must remain represented as **pending reference work** in the materialization/application result so a later HITL flow can ask the user which target was intended. Do not invent a canonical Markdown metadata field or new persistence service merely to store pending references in this phase; the durable pending-work boundary is a later HITL/application-flow decision. Until that boundary exists, Core must at least return the unresolved reference explicitly rather than silently treating it as resolved.

The note mutation itself may still proceed when the unresolved reference does not otherwise make the requested knowledge unsafe; the text remains readable but unlinked.

## References to notes created by the same request

A same-request reference does not require the referenced Markdown file to be physically persisted first. It requires the referenced unit to have a deterministic identity/path allocated first.

Therefore the write group needs a preflight before any body is written:

```text
1. validate all KnowledgeUnits
2. resolve existing targets / authorize CREATE targets
3. allocate stable identity + path for every authorized CREATE
4. bind reference occurrences to those resolved/preallocated identities
5. materialize safe [[wikilinks]] into writer facts
6. run bounded CREATE/UPDATE writers
7. validate the complete staged mutations
8. persist in a dependency-safe order / result structure
```

Identity/path allocation is not persistence. This allows unit A to contain a valid wikilink to new unit B even if B has not yet been written to disk.

The exact multi-unit persistence/partial-success contract remains separate Phase 16 work. Do not introduce a generic workflow engine or Phase 17 RequestPlan orchestration merely to support this preflight.

## Writer boundary

Luna must receive the already-bound facts. It may organize or reconcile them according to the bounded writer contract, but it is not responsible for:

- discovering which entity mention should become a link;
- resolving reference identity;
- deciding between multiple possible notes;
- allocating stable IDs or paths;
- creating new wikilinks from unrelated prose;
- repairing an ambiguous reference.

The writer should preserve supplied wikilinks as part of the authoritative intended fact. Core remains responsible for validating the final Markdown and for rejecting writer output that corrupts required bound references.

## Future HITL

Ambiguous references are a concrete future HITL use case.

```text
reference -> multiple plausible notes
        |
        v
no wikilink now
        |
        v
pending reference result
        |
        v
future HITL asks user to choose
        |
        v
bind chosen stable identity and update note safely
```

HITL should be introduced only once Odyssey has a stable application boundary capable of preserving and resuming pending work. The current Phase 16 rule is simply: **fail closed on identity, do not link ambiguously, and do not lose the fact that a reference remains pending.**

## Immediate Phase 16 execution plan

The remaining implementation order is:

1. **Reference-binding contract** — refine the reference occurrence representation so Core knows exactly where a reference belongs before any writer call.
2. **Reference-target preflight** — resolve existing targets and authorize same-request CREATE targets without persistence.
3. **CREATE identity allocation** — deterministically allocate stable IDs/paths/display identity for authorized CREATE units before body generation.
4. **Pre-writer wikilink materialization** — replace only safely bound reference occurrences with ordinary `[[wikilinks]]`; ambiguous references remain plain text and pending.
5. **CREATE materialization + UPDATE integration** — feed already-linked facts to the selected Luna/medium writer, validate the bounded output, and persist once per staged note.
6. **Remaining Phase 16 semantics** — guarded soft delete/inbound-link policy, explicit bulk cardinality, dependency/partial-success results, and type-change handling before Phase 17 orchestration.

This ordering supersedes the earlier informal idea of implementing CREATE first and adding wikilinks afterward. Reference placement must be made safe first because it changes the writer input contract for both CREATE and UPDATE.
