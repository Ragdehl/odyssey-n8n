# ADR 0007: Phase 14 request planning boundary

- Status: Accepted and implemented as the production planning boundary; its content-only write shape
  is superseded by [ADR 0009](0009-phase-15-semantic-write-planning.md) for Phase 15 preparation
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
    {"kind": "retrieve", "plan": {"query": "Odyssey", "type": null, "filters": []}},
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

The benchmark treats this distinction explicitly: retrieval actions are candidate selection, so an
extra retrieval is normally a MAJOR noise/cost defect, while an extra create action is CRITICAL because
it would authorize an unrequested future side effect. A wrong retrieval restriction that excludes a
requested candidate remains CRITICAL; an omitted safe narrowing is MAJOR. Free-text retrieval and
create-content fidelity are HUMAN REVIEW diagnostics, not deterministic safety failures.

## Controlled diagnostic protocol

Free-text `unrepresented_constraints` is replaced by a minimal controlled code collection. The strict
contract contains codes only; evaluators must not rely on diagnostic prose.

| Code | Meaning |
| --- | --- |
| `not_supported` | Requested exclusion cannot be represented. |
| `unsupported_domain_date` | Requested domain event date has no filterable field. |
| `direct_link_not_filterable` | An exact direct wikilink relation cannot be filtered. |

This is a protocol, not a new ontology: it describes planning limitations, never note relationships
or knowledge types. Predicate OR, tag OR, scoped filters, and multiple retrieval branches are no
longer limitations: separate `RetrieveAction` candidates express them safely. Ordinary semantic OR
normally remains in one semantic query; multiple named concepts alone do not justify a split.

## Production decision and consequences

Phase 14 uses the OpenAI Responses API with **gpt-5.6-sol** at low reasoning
effort. The completed frozen v3 experiment rejected Terra as the default:
Terra silently omitted one required B05 candidate region in 4/4 repetitions.
Sol's one observed S04 error was an invalid empty query, which deterministic
Core validation rejected before retrieval and which did not recur in the next
three repetitions. Sol cost about 2.3x Terra in the benchmark; that premium is
accepted for the safer planner baseline. No model router is introduced. It can
be reconsidered only after production request distribution and monthly cost are
observed.

Production renders capabilities from the current canonical schema at call time,
including caller-supplied date, time, and timezone. The frozen benchmark
capability snapshot remains historical evidence only. The production planner
locally validates every model response before returning it; invalid output
fails closed and is never exposed for execution.

The implementation still stops at the RequestPlan boundary. It does not invoke
`get_context`, create or update notes, or choose execution order. Phase 15 or a
later explicit orchestration phase may compose validated actions with Phase 13
retrieval and Phase 12 persistence.

## Historical benchmark context

Phase 14 remains deliberately narrow: it does not retrieve notes, execute `get_context`, persist
notes, resolve entities, issue SQL, retain user memory, or synthesize an answer. The next benchmark
version should freeze a new prompt and cases before any new calls, then add RequestPlan multiple-branch,
create-intent, and mixed retrieval/create cases. Its deterministic score should emphasize structural
candidate-set safety; semantic wording mismatches belong in a human-review queue. Core deterministic
evaluation must not use an LLM judge. The v1 prompt, cases, oracle, raw responses, and v1 evaluation
remain immutable historical evidence.

The prepared v2.1 experiment freezes 24 compact adversarial cases: four simple retrieval, five
multi-branch, three do-not-split, three remaining unsupported constraints, three create-only, two
mixed, one compound-create boundary, and three adversarial safety cases. Its staged future run is
Terra/low first (24 requests), then Sol/low only after human review of Terra evidence (another 24).
