# ADR 0007: Phase 14 request planning boundary

- Status: Proposed for human review (offline v2 contract prepared)
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
preserves the logical/conversational structure of mixed requests without introducing an execution graph.
Action order represents request intent, not necessarily side-effect execution order. For example, the
plan above may list `CreateNoteAction` before `RetrieveAction` because that is the user's wording, while
the downstream orchestration layer may safely retrieve prior knowledge before persisting the new note to
avoid contaminating that retrieval. This is not a blanket rule that retrievals always precede creates;
execution order must follow the request semantics when post-write state is intentionally relevant.
Phase 14 remains only the interpretation/planning boundary and does not choose that physical execution
order.

## Final proposed output contract

The contract deliberately stays smaller than a draft-note schema:

```json
{
  "actions": [
    {"kind": "retrieve", "plan": {"query": "Odyssey", "type": null, "required_tags": [], "filters": []}},
    {"kind": "create_note", "content": "Knowledge the user explicitly asked Odyssey to remember."}
  ],
  "limitations": []
}
```

`RetrieveAction.plan` is exactly one ordinary Phase 13-compatible retrieval plan. It changes no
Phase 13 semantics. A type list continues to use its existing `type` `in` filter, so common
constraints across several requested types remain one action. Conversely, different deterministic
candidate sets become several actions; the downstream retrieval layer may union and deduplicate
their results later, outside Phase 14.

`CreateNoteAction` has exactly `kind` and free-text `content`. Type, tags, properties, IDs, paths,
Markdown, persistence mode, duplicate decisions, links, and atomic decomposition are excluded.
Those fields would either invent schema-backed details or duplicate the later note-preparation and
Phase 12 persistence boundaries. One create action can preserve compound knowledge; several are
reserved for clearly independent user actions, not inferred atomic-note decomposition.

Action array order preserves logical/conversational structure. Array position is sufficient initial
branch identity: it lets a future answer layer associate results with an action without premature
action IDs or grouping. Retrieval branch evaluation treats order as irrelevant. The plan records no
physical execution dependency: a later orchestrator may retrieve prior knowledge before persisting a
preceding create intent when needed to avoid contaminating the answer.

## Controlled diagnostic protocol

Free-text `unrepresented_constraints` should be replaced by a minimal controlled code collection.
Optional human detail may accompany a code, but evaluators must rely on the code rather than prose.

| Code | Meaning |
| --- | --- |
| `not_supported` | Requested exclusion cannot be represented. |
| `unsupported_domain_date` | Requested domain event date has no filterable field. |
| `direct_link_not_filterable` | An exact direct wikilink relation cannot be filtered. |

This is a protocol, not a new ontology: it describes planning limitations, never note relationships
or knowledge types. Predicate OR, tag OR, scoped filters, and multiple retrieval branches are no
longer limitations: separate `RetrieveAction` candidates express them safely. Ordinary semantic OR
normally remains in one semantic query; multiple named concepts alone do not justify a split.

## Consequences and future benchmark v2

Phase 14 remains deliberately narrow: it does not retrieve notes, execute `get_context`, persist
notes, resolve entities, issue SQL, retain user memory, or synthesize an answer. The next benchmark
version should freeze a new prompt and cases before any new calls, then add RequestPlan multiple-branch,
create-intent, and mixed retrieval/create cases. Its deterministic score should emphasize structural
candidate-set safety; semantic wording mismatches belong in a human-review queue. Core deterministic
evaluation must not use an LLM judge. The v1 prompt, cases, oracle, raw responses, and v1 evaluation
remain immutable historical evidence.

The prepared v2 experiment freezes 24 compact adversarial cases: four simple retrieval, five
multi-branch, three do-not-split, three remaining unsupported constraints, three create-only, two
mixed, one compound-create boundary, and three adversarial safety cases. Its staged future run is
Terra/low first (24 requests), then Sol/low only after human review of Terra evidence (another 24).
