# Phase 14 RequestPlan benchmark v2 (offline draft)

This is a new, frozen-before-calls experiment. It does not alter Phase 14 retrieval-plan v1, its 366 raw responses, or evaluator v2.1 historical evidence.

## Contract under test

```text
RequestPlan
  actions[] (ordered logical request structure)
    RetrieveAction { kind: "retrieve", plan: RetrievalPlan }
    CreateNoteAction { kind: "create_note", content }
  limitations[]
```

Every `RetrieveAction` owns exactly one unchanged Phase 13-compatible plan (`query`, optional exact `type`, all-of `required_tags`, and validated filter list). Several actions represent independent deterministic candidate sets. Retrieval action order is not scored; a later orchestration layer can retain its array position as branch identity. No action IDs, grouping field, graph, or dependencies are justified yet.

`CreateNoteAction.content` preserves the knowledge explicitly requested for memory. It intentionally has no type/tag hints, stable ID, path, Markdown, lifecycle fields, relation model, persistence instruction, or final atomic-note decomposition. The later preparation layer may decide note structure; Phase 12/Core remains responsible for deterministic IDs and persistence.

The only remaining limitation codes are `not_supported`, `unsupported_domain_date`, and `direct_link_not_filterable`. Predicate OR, tag OR, scoped filters, and independent branches now become separate retrieval actions rather than limitations.

## Evaluation

The oracle compares deterministic candidate branches as an unordered set. A false hard filter, collapsed globally ANDed branch, missing whole candidate branch, invalid action shape, or extra independently constrained retrieval branch is CRITICAL. Omitted safe narrowing is MAJOR. Query wording and create-content fidelity are HUMAN REVIEW, never automated CRITICAL.

## Future staged run (requires human approval)

The default future invocation executes the 24 cases once with `gpt-5.6-terra` / `low`. Only after reviewing those append-only results should `gpt-5.6-sol` / `low` be added as the quality reference. This is 24 paid requests for Terra, then 24 for Sol if approved: 48 maximum for the initial staged comparison. Each request is independent, retains provider usage/cached-token counters, latency, estimated cost, immutable metadata hashes, and append-only raw evidence. The shared system prompt/schema prefix is cache-stable.

Do not run this harness until paid execution is explicitly approved.
