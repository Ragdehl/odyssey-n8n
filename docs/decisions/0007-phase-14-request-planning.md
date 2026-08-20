# ADR 0007: Phase 14 request planning boundary

- Status: Proposed for human review
- Date: 2026-08-20

## Context

Phase 14 benchmark evidence shows that a single globally-ANDed `RetrievalPlan` cannot safely express
requests with independently constrained retrieval branches. For example, a request for Odyssey notes
updated today and n8n notes created yesterday must not apply both date predicates to every candidate.
The same request can also ask Odyssey to remember new knowledge. Phase 13 already accepts one
validated retrieval plan at its retrieval boundary, and Phase 12 owns deterministic Markdown
persistence and validation.

## Decision

Keep Phase 14 as an interpretation and planning boundary. Its future output should be an ordered
`RequestPlan` containing a small discriminated action collection:

```text
user request
    |
    v
RequestPlan.actions (ordered)
    |-- RetrieveAction -> one existing RetrievalPlan
    |-- RetrieveAction -> one independent RetrievalPlan
    `-- CreateNoteAction -> intent/content for later note preparation
```

`RetrieveAction` wraps exactly one safe `RetrievalPlan`; it does not retrieve Markdown or call
`get_context`. Multiple actions represent independent candidate sets, rather than adding unsupported
OR, branch scope, or per-type conditions to a global plan.

`CreateNoteAction` represents the user-supplied knowledge intent and content required by a later
preparation/decomposition layer. It must not generate a final stable note ID, write Markdown, index
SQLite, resolve semantic duplicates, or invent a generic relationship ontology. A later deterministic
Core boundary generates the stable ID, validates schema-backed notes, serializes authoritative Markdown,
and updates derived SQLite state through the existing persistence path.

Examples:

```text
¿Qué modifiqué hoy sobre Odyssey y qué escribí ayer sobre n8n?
  -> RetrieveAction(query="Odyssey", updated_at=today)
  -> RetrieveAction(query="n8n", created_at=yesterday)

Apunta que quiero usar Sol para Phase 14 y dime qué había pensado antes sobre esto.
  -> CreateNoteAction(intent/content="quiero usar Sol para Phase 14")
  -> RetrieveAction(query="qué había pensado antes sobre esto")
```

The action list is preferred over separate `retrieval_plans` and `create_notes` collections because it
preserves the request's order for mixed operations without introducing an execution graph. The latter
shape is slightly smaller today but loses ordering or needs a second ordering field as soon as requests
mix actions. This is not a LangGraph use case: Phase 14 plans explicit actions and does not need
stateful iteration.

## Controlled diagnostic protocol for a future benchmark and interpreter

Free-text `unrepresented_constraints` should be replaced by a minimal controlled code collection.
Optional human detail may accompany a code, but evaluators must rely on the code rather than prose.

| Code | Meaning |
| --- | --- |
| `predicate_or` | Deterministic predicate alternatives need separate branches. |
| `tag_or` | Tag alternatives cannot be represented by ANDed required tags. |
| `not_supported` | Requested exclusion cannot be represented. |
| `scoped_filter` | A condition applies only to one branch or type. |
| `multiple_retrieval_branches` | The request needs independent retrieval plans. |
| `unsupported_domain_date` | Requested domain event date has no filterable field. |
| `direct_link_not_filterable` | An exact direct wikilink relation cannot be filtered. |

This is a protocol, not a new ontology: it describes planning limitations, never note relationships
or knowledge types.

## Consequences and future benchmark v2

Phase 14 remains deliberately narrow: it does not retrieve notes, execute `get_context`, persist
notes, resolve entities, issue SQL, retain user memory, or synthesize an answer. The next benchmark
version should freeze a new prompt and cases before any new calls, then add RequestPlan multiple-branch,
create-intent, and mixed retrieval/create cases. Its deterministic score should emphasize structural
candidate-set safety; semantic wording mismatches belong in a human-review queue. Core deterministic
evaluation must not use an LLM judge. The v1 prompt, cases, oracle, raw responses, and v1 evaluation
remain immutable historical evidence.
