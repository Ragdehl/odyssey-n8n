# Phase 16 reference binding and pre-writer wikilinks

## Purpose

This document is the canonical contract for materializing semantic `KnowledgeUnit.references` into ordinary Markdown `[[wikilinks]]` during Phase 16.

Phase 15 preserves logical references between knowledge units and, in Phase 16.5A, preserves each
reference occurrence before any semantic writer call. The closed `KnowledgeReference(target_index,
role, mention)` shape carries the target unit, semantic role, and original human-readable wording.
Phase 16 must still bind references **before** the CREATE/UPDATE writer sees the facts that contain
them.

The goal is to keep reference placement deterministic and avoid a second LLM call or post-hoc text guessing.

## Phase 16.5B target preflight

Phase 16.5B adds a deterministic, non-persisting preflight table indexed by ordered unit index:

```text
validated WriteAction -> decide each KnowledgeUnit once
        | UPDATE -> existing ID + authoritative path + metadata name
        | CREATE -> full UUID + <name> - <full-id>.md
        ` NEEDS_CLARIFICATION -> reason + known candidate IDs
```

Reference occurrences consume this table through `target_index`; they do not invoke resolution a
second time. CREATE names use `target.entity` when present, otherwise the human-readable
`target.query`. UUID allocation is injectable for deterministic tests. The preflight performs no
Markdown writes, persistence, writer/model calls, or wikilink rendering. `name` is canonical
metadata; the filename is a stable creation-time label and always contains the full stable ID.

## Phase 16.5C scope

Phase 16.5C is deliberately small. It does not resolve identity, allocate IDs, persist notes, run
HITL, or decide whether occurrence wording should become a durable alias. It consumes the already
validated `KnowledgeUnit` plus the Phase 16.5B preflight table and produces writer-ready facts.

```text
{{ref:N}}
    |
    +--> target has one safe path
    |       -> [[vault/path-without-.md|mention]]
    |
    `--> target still needs clarification
            -> mention as plain text
            + explicit PendingReference result
```

The link target is always derived from the authoritative existing path or the preallocated CREATE
path. The display text is the occurrence-local `mention`. The renderer never performs a second
identity lookup and never guesses from a human name or alias.

Phase 16.5C itself remains non-persisting. Durable pending-reference artifacts are a later
application/HITL concern described below.

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
        `--> ambiguous/unresolved -> plain mention + explicit pending reference
        |
        v
Core materializes safe references as [[wikilinks]]
        |
        v
Luna receives facts with resolved wikilinks already present
        |
        v
bounded CREATE/UPDATE body operation
        |
        v
Core validates and persists
```

Do **not** ask a later LLM to rediscover which words in writer output represented a reference. Do **not** apply a blind string replacement after Luna has rewritten or reorganized the sentence.

## Reference occurrence contract

Phase 16.5A freezes a reserved internal planner marker. Every semantic reference occurrence is
replaced in its fact by `{{ref:N}}`, where `N` is the zero-based index into that same
KnowledgeUnit's `references` array. The matching `KnowledgeReference.mention` preserves the original
human-readable wording, even when it differs from the referenced unit's canonical query.

```text
fact:
  "Compré {{ref:1}} en {{ref:0}}."

references:
  ref:0 -> unit 0, role=store, mention="Carrefour Balma"
  ref:1 -> unit 1, role=product, mention="Leche Pascual"
```

The same marker may occur repeatedly. Every reference must have at least one marker in that unit's
facts; every marker must resolve to a valid local reference index. Malformed or out-of-range markers,
or planner-generated raw Markdown wikilinks, fail closed. References still cannot point to the
KnowledgeUnit itself. A unit used only as a reference target may have no facts; its occurrence marker
belongs to the referencing unit.

Markers are an internal planner contract, not user-authored Markdown syntax. They preserve semantic
occurrence placement only; Core does not use offsets, string similarity, fuzzy matching, another LLM,
or Markdown AST parsing to rediscover placement. The Sol/low planner is explicitly instructed not to
mark names used only to identify the target and not to create inverse relationship references.

After safe identity binding, a fact may become:

```text
"Compré [[Leche Pascual - <full-id>|Leche Pascual]] en [[Carrefour Balma - <full-id>|Carrefour Balma]]."
```

If a target lives in a folder, use the vault-relative path without the `.md` suffix:

```text
[[products/Leche Pascual - <full-id>|Leche Pascual]]
```

The invariant is that **reference placement is decided before the writer and can be materialized by
Core without semantic inference**. Phase 16.5C replaces the temporary UPDATE fail-closed guard with
pre-writer rendering; it does not reopen target resolution.

The actual Obsidian link target must be derived deterministically from the authoritative existing path or the preallocated CREATE path. A primary name or alias alone is never sufficient evidence for the physical link target when it could be ambiguous.

## Mention and alias separation

`mention` and `aliases` are related but not equivalent.

```text
mention
= how this reference is worded in this occurrence

alias
= a reusable identity expression worth storing on the target note
```

Some mentions may be good future aliases:

```text
name: Carrefour Balma
mention: Carrefour
```

or:

```text
name: Marta García
mention: la amiga de Laura
```

Other mentions are transient and should not become durable identity vocabulary:

```text
mention: la chica con la que cenamos ayer
```

Phase 16.5C therefore **does not automatically promote mentions to aliases**. It also does not
forbid such promotion forever. Deciding whether a mention is a stable reusable identity phrase is a
separate semantic write decision and should be added only with an explicit contract/evidence path,
not hidden inside deterministic wikilink rendering.

## Existing referenced notes

When a reference points to knowledge that already exists, reuse the existing Phase 9-11 identity stack. The planner does not choose the repository note; Core binds the reference only after one safe stable identity has been resolved.

If several existing notes remain plausible, or identity otherwise remains ambiguous, Phase 16 must not guess a canonical target.

For Phase 16.5C:

```text
unique safe target    -> materialize [[path|mention]]
ambiguous target      -> keep mention as plain text + PendingReference
unresolved target     -> keep mention as plain text + PendingReference unless CREATE is independently authorized
```

An ambiguous or unresolved reference must remain represented as **pending reference work** in the materialization/application result so a later HITL flow can ask the user which target was intended. Phase 16.5C does not persist that workflow state itself. Until a durable boundary exists, Core must at least return the unresolved reference explicitly rather than silently treating it as resolved.

When ambiguity is specifically between several known existing notes, preserve the **candidate stable identities** as part of that pending work whenever the resolver has them. This lets future HITL present the real choices without re-running semantic discovery and avoids losing information such as "the reference could be Marta García or Marta López".

The note mutation itself may still proceed when the unresolved reference does not otherwise make the requested knowledge unsafe; the text remains readable and the pending ambiguity remains explicit.

## Preferred durable pending-reference direction

The approved future direction is to make unresolved ambiguity navigable in the Markdown graph once a
stable pending-work/HITL boundary exists.

Conceptually, Odyssey may create a small **internal pending-reference Markdown artifact**:

```text
pending reference artifact
    mention: "Una Marta"
    candidates:
      -> [[Marta García - <id>|Marta García]]
      -> [[Marta López - <id>|Marta López]]
```

A source note could then temporarily contain a human-readable link such as:

```text
[[pending/Marta-ambiguity-<uuid>|Una Marta]]
```

This is preferable to inventing one candidate as the answer because the graph itself preserves the
ambiguity and its candidate set. Once HITL or later evidence resolves the identity, the source link
should normally be replaced with the real target and the pending artifact archived or removed.
Keeping the ambiguity artifact permanently as a proxy is not the default direction because it would
pollute the knowledge graph with a false long-lived entity.

Important boundaries:

- the pending artifact is **workflow state**, not automatically a canonical user-knowledge note;
- do not add a canonical Odyssey note type merely to implement it;
- its storage location, lifecycle, cleanup, and backlink replacement need the stable application/HITL
  boundary before implementation;
- Phase 16.5C does not create or persist this artifact.

This direction preserves the user's desired future UX without coupling simple reference rendering to
persistence or HITL prematurely.

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

## No automatic inverse writes

A semantic reference or wikilink authorizes only the fact the user actually supplied. Odyssey must not automatically create a mirrored or inverse fact in the referenced note merely to make reverse questions easier to answer.

For example, if the user records:

```text
Laura is responsible for [[Marta]].
```

Odyssey may CREATE/UPDATE Laura and bind the reference to Marta, but it must not also update Marta with a generated inverse fact such as `Responsible: [[Laura]]` unless the user request independently requires that mutation or a future explicit domain rule justifies it.

This avoids duplicated knowledge, extra writes, synchronization problems, and invented relation semantics. Reverse natural-language questions should first rely on ordinary semantic context retrieval, whose embedding projection already renders wikilinks as readable entity text. Explicit backlink/graph traversal remains a separate retrieval capability for structural graph questions or a future evidence-backed recall supplement. See [Semantic Candidate Retrieval](semantic-retrieval.md#relationship-retrieval-direction).

## Writer boundary

Luna must receive the already-bound facts. It may organize or reconcile them according to the bounded writer contract, but it is not responsible for:

- discovering which entity mention should become a link;
- resolving reference identity;
- deciding between multiple possible notes;
- allocating stable IDs or paths;
- creating new wikilinks from unrelated prose;
- repairing an ambiguous reference.

The writer should preserve supplied wikilinks as part of the authoritative intended fact. Core remains responsible for validating the final Markdown and for rejecting writer output that corrupts required bound references.

Because Phase 16.5C materially changes writer input from plain fact text to already-linked Markdown,
focused live evidence must be rerun with the selected production `gpt-5.6-luna` / medium writer before
treating UPDATE-with-links behavior as validated. This is a focused regression check, not model
selection.

## Future HITL

Ambiguous references are a concrete future HITL use case.

```text
reference -> multiple plausible notes
        |
        v
Phase 16.5C: plain mention + PendingReference
        |
        v
future durable pending artifact may link the candidate notes
        |
        v
HITL asks user to choose
        |
        v
replace source occurrence with real target
        |
        v
archive/remove pending artifact
```

HITL should be introduced only once Odyssey has a stable application boundary capable of preserving and resuming pending work. The current Phase 16.5C rule is simply: **do not guess identity, preserve the mention and candidate set, and keep rendering deterministic.**

## Immediate Phase 16 execution plan

The remaining implementation order is:

1. **Reference-binding contract** — refine the reference occurrence representation so Core knows exactly where a reference belongs before any writer call. ✅
2. **Reference-target preflight** — resolve existing targets and authorize same-request CREATE targets without persistence. ✅
3. **CREATE identity allocation** — deterministically allocate stable IDs/paths/display identity for authorized CREATE units before body generation. ✅ (owned by Phase 16.5B)
4. **Pre-writer wikilink materialization — Phase 16.5C** — replace safely bound reference occurrences with ordinary `[[path|mention]]`; unresolved references remain plain mentions plus explicit pending results. No persistence or HITL.
5. **CREATE materialization + UPDATE integration** — feed already-linked facts to the selected Luna/medium writer, validate the bounded output, and persist once per staged note.
6. **Remaining Phase 16 semantics** — guarded soft delete/inbound-link policy, explicit bulk cardinality, dependency/partial-success results, type-change handling, and later durable pending-reference/HITL lifecycle before or alongside the stable application boundary as evidence dictates.

This ordering supersedes the earlier informal idea of implementing CREATE first and adding wikilinks afterward. Reference placement must be made safe first because it changes the writer input contract for both CREATE and UPDATE.
