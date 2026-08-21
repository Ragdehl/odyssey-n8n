# Phase 14 RequestPlan benchmark v2.2 — READY FOR PAID EXECUTION

This is a new, frozen-before-calls experiment. It does not alter Phase 14 retrieval-plan v1, its 366 raw responses, or evaluator v2.1 historical evidence. The v2.2 oracle and contract are locked; paid execution still requires separate human approval.

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

The evaluator measures total retrieval coverage after downstream union/deduplication, not 1:1 branch
pairing. It proves equivalent branches, one broad branch covering multiple oracle branches, and a
finite `type` set partitioned across otherwise equivalent actions. Type partitioning is MAJOR because
it adds cost. If coverage cannot be proven, the evaluator stays conservative unless a concrete
narrowing is present; a globally ANDed branch is CRITICAL because it demonstrably excludes a region.

`created_at`, `updated_at`, `birth_date`, and `entry_date` are semantic intervals, including endpoint
inclusivity and timezone-aware date-times. A containing actual interval is MAJOR when broader, equal
is PASS, and a narrower, incomplete-overlap, or disjoint interval is CRITICAL. Other deterministic
dimensions use recall-first containment: broader type or `eq`/`in` values are MAJOR; narrower values,
wrong fields, and extra all-of tag/`contains` restrictions are CRITICAL. Omitted requested filters are
MAJOR. An extra retrieval action is MAJOR (noise/cost); an extra create action is CRITICAL because it
would authorize an unrequested future side effect. Query and create-content aids are HUMAN REVIEW only.

Logical mixed action order is evaluated where the oracle declares it, but it remains MAJOR-only and
does not prescribe physical execution. The Structured Outputs schema uses the conservative strict
subset of closed objects, required properties, enums, arrays/items, and `anyOf`; local validation
remains defense in depth for non-empty values and type/filter scope. The prompt renders concise
filter capabilities from the same frozen, schema-aligned contract.

## Future staged run (requires human approval)

Immutable metadata plans both configurations, while execution selects one: `--configuration terra`
(default), or `--configuration sol` only after human approval. The same directory can therefore
accumulate append-only evidence without metadata mutation: 24 Terra/low requests, human review, then
+24 Sol/low only if approved. `--target-repetitions` permits 1–4 total runs and `--case-id` restricts
future repeats to selected cases; no repeats are automatic.

Logical identity is `(model, reasoning_effort, test_id, repetition)`. A successful logical request is
never rerun on resume. A failure remains evidence and retries only with `--retry-failures`, as a new
`attempt` for the same repetition. Aggregation selects the latest successful attempt, otherwise the
latest failure, so retries never count as quality repetitions.

`pricing.json` is the 2026-08-21 official OpenAI API Standard/short-context USD snapshot: Terra
$2.50/$0.25/$3.125/$15.00 and Sol $5.00/$0.50/$6.25/$30.00 for ordinary input/cached input/cache
writes/output per 1M tokens. `input_tokens` is normalized as total input minus cached reads and cache
writes; all three input categories are then billed exactly once. Raw evidence records actual cached and
write counters, prompt/schema hashes, and the stable cache strategy without assuming a hit or write.

One user request still produces one planner LLM call, even when its `RequestPlan` contains several
`RetrieveAction` entries; those actions execute locally/downstream and do not create additional planner
calls. Explicit prompt caching is useful across successive planning requests because the large
system/schema prefix is stable. With GPT-5.6 pricing, an explicit cache write costs more than ordinary
input, while later cache reads are much cheaper, so reuse can become worthwhile across repeated calls.
This benchmark enables explicit caching and records provider counters; no TTL field is added because the
repository/SDK payload shape does not support one, so provider TTL policy applies. Production caching
policy and TTL will be finalized during Phase 14 implementation, not in this benchmark architecture.

Do not run this harness until paid execution is explicitly approved.
