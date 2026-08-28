# Future semantic request history

Status: **preserved product direction; representation deferred until after the first real E2E**

## Product goal

Odyssey should eventually be able to retrieve not only canonical knowledge, but also useful history about what the user asked it to do, how the validated planner decomposed the request, and which knowledge objects were affected.

Representative questions include:

```text
"¿Qué te pedí ayer?"
"¿De qué hablamos el 12 de agosto?"
"¿Qué cambiaste cuando te dije que Marta se mudaba?"
"¿Qué notas creamos cuando te hablé de Marta?"
```

This remains an intended capability. It is deliberately **not** on the Phase 17A critical path.

## Revised representation decision

The earlier direction proposed adding a canonical note type named `user_request` to `config/note-schema.json`. Do **not** implement that direction yet.

Adding `type=user_request` now would force normal knowledge systems to carry a special internal-type exception before real end-to-end evidence proves that coupling is useful:

- ordinary identity resolution;
- semantic/context retrieval;
- bulk selection;
- CREATE authorization;
- planner schema projections;
- calculations and other future selectors.

Request history is application/history state, not automatically canonical user knowledge. After the first real E2E exists, reassess the smallest representation from observed query and operational needs. Markdown may still be appropriate, but the representation need not be an ordinary canonical knowledge type.

Therefore, until that later decision:

- do not add `user_request` to the canonical note schema;
- do not modify normal retrieval/resolution/bulk behavior for request history;
- do not expose an internal history type to the production planner;
- do not build a second semantic search engine solely for request history.

## Stable correlation through request_id

Phase 17A introduces one stable `request_id` for every logical Odyssey request. Any future request-history implementation must reuse it.

```text
logical request
      |
      +--> request_id
      |
      +--> 17A ApplicationResult
      +--> 17B pending work
      +--> 17C Git metadata
      `--> future request-history record
```

Do not invent an independent history identifier when `request_id` already identifies the logical request.

## Minimum useful evidence

Whatever representation is chosen later should be able to preserve useful human- and machine-readable evidence such as:

- stable `request_id`;
- exact user request received by the Odyssey application boundary;
- validated `RequestPlan` or deterministic equivalent rendering;
- execution status;
- affected stable note IDs and operation types where useful;
- failed/deferred/candidate IDs needed to understand partial success;
- timestamps and application correlation metadata as justified by the later contract.

Do **not** persist hidden chain-of-thought, private model reasoning, or every intermediate model response. The validated planner output and typed application result are the auditable semantic boundaries.

## Relationship with Git

Phase 17C local Git history should correlate through the same `request_id`, preferably with:

```text
Odyssey-Request: <request_id>
```

A future request-history record should not be required to contain the SHA of the same Git commit that contains that record. The commit SHA depends on the committed tree, so storing it inside that tree creates circular self-reference. Resolve request history to Git through `request_id` instead.

## Relationship with operational tracing

Semantic request history and operational tracing are separate concerns.

Request history answers product questions such as what the user asked and what Odyssey changed. Operational tracing concerns latency, model calls, token/cost metadata, retries, failures, stack traces, n8n execution identifiers, and similar diagnostics.

Phase 17A propagates `request_id`; full operational tracing is deferred until Phase 18/19 reveals the real boundaries worth instrumenting. Introduce a separate `trace_id` only if actual retries/subtraces prove that one request can require several operational traces.

Neither request history nor tracing may store hidden model reasoning.

## Safety rules for the future capability

- request history must not become canonical truth for facts already represented in knowledge notes;
- ordinary knowledge retrieval must not be contaminated merely because history repeats words such as `Marta` or `Lyon`;
- semantic similarity alone must not make internal history appear in ordinary answers;
- request history should remain useful even for requests that produced no canonical mutation, if later product evidence justifies storing those requests;
- representation, retention, indexing, and visibility rules must be explicit before implementation.

## Deferred decisions

After Phase 18 proves the first real E2E, decide from evidence:

1. whether request history should use Markdown, SQLite-derived storage, or another small internal representation;
2. whether every request or only meaningful requests should be persisted;
3. whether read-only requests are included;
4. whether final answer text is stored, summarized, or omitted in favor of structured outcome evidence;
5. how explicit history retrieval is represented at the planner/application boundary;
6. how history is indexed without contaminating ordinary knowledge retrieval;
7. path/layout and retention policy if Markdown is selected;
8. how history and Git evidence are presented together through `request_id`.

Do not implement these decisions in Phase 17A merely to preserve the future product goal.
