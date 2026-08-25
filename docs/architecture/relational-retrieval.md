# Relational retrieval over ordinary wikilinks

## Purpose

Preserve the retrieval consequence of Odyssey's simple-link write model: knowledge may be stored only on the note that naturally states it, without duplicating an inverse fact onto the linked note.

Example:

```text
Laura note:
  "Laura is responsible for [[Marta]]."

Marta note:
  no mirrored "Laura is responsible for Marta" fact
```

A later question such as "Who was responsible for Marta?" must still be answerable.

## Simplest retrieval direction

Do not introduce typed edges or automatically mirror relations merely to make inverse questions easier. Use the ordinary wikilink graph only to generate a small candidate set, then use the requested relation semantics against the source-note content.

```text
relational question about Marta
        |
        v
resolve Marta to one stable note identity
        |
        v
incoming one-hop backlinks to Marta
        |
        v
candidate source notes (for example Laura)
        |
        v
rank/read those source notes using the original semantic question
        |
        v
answer from the sentence that states the relation
```

For `Laura is responsible for [[Marta]]`, the link tells Core that Laura is structurally connected to Marta. The prose tells the semantic direction and meaning (`responsible for`). The edge itself does not need a type such as `responsible_for`.

## One hop by default for inverse facts

Inverse relation lookup is not the same as arbitrary graph traversal. When the requested fact can be recovered from a note that directly links to the resolved anchor, prefer an incoming `max_depth=1` lookup.

Only use broader/multi-hop traversal when the user question genuinely requires a chain of relationships.

This avoids:

- mirrored facts in both notes;
- a mandatory typed-relation ontology;
- expensive graph expansion for ordinary inverse questions;
- inconsistent duplicated statements after later updates.

## Planner implication

The existing `LinkScope(direction=incoming|outgoing|both, max_depth=...)` shape can represent this execution path. Before graph retrieval is implemented, benchmark/refine planner guidance so ordinary natural-language relation questions that logically require backlink evidence can request the appropriate graph scope even when the user does not literally say "linked", "backlink", or "related".

This is different from a direct question such as `What do I know about Marta?`, which should continue to read Marta's own note with `link_scope=null`.

Examples:

```text
"What do I know about Marta?"
-> direct Marta note only

"Who was responsible for Marta?"
-> resolve Marta
-> incoming backlinks, depth 1
-> semantic filtering of backlink source notes

"What project does Marta's manager work on?"
-> may require more than one hop; only widen traversal if the planned semantics explicitly require it
```

## Index direction

When implemented, a rebuildable link table/index is the simplest execution structure:

```text
source_note_id | target_note_id
```

It is derived from authoritative Markdown wikilinks and can support deterministic incoming/outgoing lookup. It is not a new source of truth.

The first implementation should prove one-hop incoming/outgoing retrieval before adding recursive graph machinery.
