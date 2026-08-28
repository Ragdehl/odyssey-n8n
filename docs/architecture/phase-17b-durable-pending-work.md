# Phase 17B durable pending work

Status: **implemented; deterministic verification passed**

This document is the canonical contract for Phase 17B. Phase 17A can now execute one validated
`RequestPlan` and return typed deferred/failed/delegated evidence, but that evidence disappears when
the process ends. Phase 17B makes only actionable incomplete work durable so later HITL or retry logic
does not have to reconstruct the user's intent or rerun semantic discovery from scratch.

## Objective

Persist actionable incomplete Odyssey work after a validated request has executed, while keeping that
workflow state separate from canonical user knowledge.

```text
raw request
    |
    v
validated RequestPlan
    |
    v
17A execution
    |
    +--> completed work --------------------> no pending record
    |
    `--> deferred / failed / delegated work
                    |
                    v
             17B pending projection
                    |
                    v
       durable internal application state
```

The record must preserve enough validated intent and result evidence for a later human-in-the-loop or
retry boundary to understand what remains incomplete without asking Sol to reinterpret the original
request.

## Actual problem

Phase 17A already returns:

- one stable `request_id`;
- ordered action results;
- per-unit success/deferred/failure evidence;
- every unresolved `DependencyEvidence` value;
- candidate stable IDs;
- bulk per-note outcomes;
- delegated work.

That is enough to explain the current execution result, but a later retry also needs the corresponding
validated planner action/unit. Persisting only strings such as `DEPENDENCY_FAILED` would lose the
normalized work that must eventually be resolved or retried.

Phase 17B therefore records the **validated planned action together with its incomplete execution
evidence**. It does not store hidden model reasoning or raw provider responses.

## Architecture challenge

### Reconsidered direction: Markdown pending artifacts inside the knowledge vault

Do **not** initially put pending-work Markdown files under the canonical knowledge vault.

`VaultRepository.list_markdown_paths()` recursively returns every regular `.md` file beneath the vault.
The context/index and deterministic selection paths consume that canonical listing. A directory such as
`vault/pending/*.md` would therefore require special exclusions throughout existing knowledge storage,
validation, indexing, resolution, and bulk-selection paths or would be mistaken for ordinary notes.

That complexity is not justified merely to make internal workflow state visible in Obsidian.

### Rejected direction: `runtime/`

Do not store pending work beneath `/data/odyssey/runtime`. The current storage contract defines that
directory as rebuildable/disposable. Pending work is specifically the information Odyssey cannot safely
reconstruct after the process exits.

### Rejected direction: canonical note type

Do not add `pending`, `pending_reference`, `user_request`, or any equivalent internal workflow type to
`config/note-schema.json`. Pending work is application state, not a knowledge entity.

### Revised direction

Add one durable operational-state sibling beneath the existing data root:

```text
/data/odyssey/
├── vault/                 # canonical user knowledge
├── config/
├── state/                 # durable non-knowledge application state
│   └── pending/
└── runtime/               # rebuildable/disposable data
```

Use a small JSON record format for Phase 17B. JSON is chosen because the state is structured workflow
evidence, not prose knowledge, and because using a non-Markdown format prevents accidental inclusion in
canonical Markdown scans without adding exclusion rules.

Architecture challenge result: **PROCEED with the revised separate-state design.**

Human decision: **APPROVED** — the merged Phase 17B architecture contract approved the persistent
non-rebuildable application-state directory and deterministic JSON representation.

## Source-of-truth boundary

The sources of truth remain distinct:

```text
Git repository
    -> application schema + code + architecture

/data/odyssey/vault
    -> canonical user knowledge

/data/odyssey/state
    -> durable Odyssey workflow/application state

/data/odyssey/runtime
    -> derived/rebuildable indexes and caches
```

Pending state is authoritative only for the fact that Odyssey has incomplete workflow work. It is never
authoritative for user knowledge already represented in canonical notes.

The pending store must not participate in:

- `VaultRepository.list_markdown_paths()`;
- context embeddings;
- semantic candidate retrieval;
- entity resolution;
- deterministic bulk membership;
- canonical note validation;
- normal knowledge answers.

## Record granularity and identity

Use **one pending-work record per logical request**, keyed by the existing Phase 17A `request_id`.

Do not introduce another `pending_id` unless later evidence proves one request needs independently
addressable durable records.

Conceptually:

```text
request_id = R123

/data/odyssey/state/pending/R123.json
    |
    +--> original user request
    +--> application status
    +--> affected successful note IDs
    +--> planner limitations
    `--> only actions that remain incomplete
            +--> validated planned action snapshot
            `--> matching typed execution evidence
```

A request with several incomplete units still produces one file. This keeps request correlation simple
and avoids proliferating tiny artifacts.

## Minimum record contract

The exact Python dataclass names are implementation details, but the persisted representation must
contain at least:

- a fixed format marker such as `odyssey_pending_work`;
- `format_version: 1`;
- the stable `request_id`;
- creation timestamp;
- `status: open` for the initial Phase 17B lifecycle;
- the exact user request received by the application boundary;
- the aggregate Phase 17A application status;
- planner limitations when present;
- successful affected stable note IDs from the same request;
- one ordered snapshot for each incomplete action.

Each incomplete-action snapshot must preserve:

1. the original `action_index`;
2. the normalized validated planned action needed to understand/retry the work;
3. the matching `ActionResult` evidence relevant to that action.

For write actions, preserving the whole validated `WriteAction` snapshot plus its typed result is
preferred over extracting only a single failed unit, because `KnowledgeReference.target_index` values
are local to the original action and need their surrounding unit table to remain meaningful.

The record is **evidence, not an automatic replay command**. A later HITL/retry boundary must explicitly
choose which pending work to resolve or retry and must reapply current revision/schema safety checks.
It must never blindly replay every unit in the saved action.

## What counts as pending work

After planning succeeded, create a pending record when at least one action is not fully completed,
including representative cases such as:

- ambiguous/unresolved reference dependencies;
- `NEEDS_CLARIFICATION` target decisions;
- failed CREATE/UPDATE/DELETE/migration units;
- dependency-blocked units;
- CREATE cycles;
- partial/failed deterministic bulk UPDATE results;
- unsupported-but-preserved capabilities such as current link-scope execution;
- `DelegateAction` work awaiting Phase 18 routing.

Do not create a pending record for a fully completed request.

A planner/provider failure before a valid `RequestPlan` exists is **not** Phase 17B pending work. There
is no validated normalized action to preserve. Operational tracing/retry policy for those failures
belongs to Phase 19 rather than turning raw failures into semantic workflow records.

## Application integration

Phase 17B extends the existing application boundary rather than introducing a second orchestrator.
`execute_request()` already has the raw request and validated `RequestPlan` in scope while building its
`ApplicationResult`, so the pending recorder should consume those existing values directly.

Prefer one explicit injected boundary conceptually similar to:

```python
class PendingWorkRecorder(Protocol):
    def record(self, *, user_request, plan, result, created_at) -> str: ...
```

The recorder:

- decides deterministically whether the result requires a record;
- projects only incomplete actions plus safe request-level evidence;
- persists one create-only record;
- returns the durable record identifier, initially the `request_id`.

Do not call the planner again and do not expose a second semantic interpretation path merely to build
pending state.

## Durability evidence in `ApplicationResult`

Pending persistence must never fail silently.

Extend the application result with the smallest typed durability outcome, conceptually:

```text
pending_work.required
pending_work.persisted
pending_work.record_id
pending_work.error
```

Representative behavior:

```text
completed request
    -> required=false

needs_attention / partial / post-plan failure
    -> required=true
    -> persisted=true + record_id=request_id

pending store missing/fails
    -> required=true
    -> persisted=false + bounded error
```

A pending-store failure does **not** roll back successful knowledge mutations. Preserve the Phase 17A
application status and affected IDs, and surface the separate durability failure so Phase 18 can alert
or retry it explicitly.

If Phase 17B remains temporarily optional at the Python API boundary for backward compatibility, an
incomplete result without a configured recorder must still report that durable pending work was
required but not persisted. Silent dropping is not acceptable.

## Pending storage boundary

Implement the smallest dedicated contained repository for pending records rather than generalizing
`VaultRepository` into an application-state framework.

Initial responsibilities:

- accept one configured existing `state/pending` root;
- reject unsafe request IDs/paths;
- create one UTF-8 JSON record without overwriting an existing request record;
- read one record by request ID;
- list existing record IDs deterministically;
- reject malformed/incompatible record format on read.

Do not create a database or a generic state store.

The production/deployment directory may be created when the application is actually wired to the local
environment. Repository tests should use isolated temporary directories; Phase 17B does not need to
modify real personal data under `/data/odyssey` to prove the Core contract.

## Serialization

Use deterministic human-readable UTF-8 JSON, with stable field names and a terminating newline.

The serializer must explicitly project supported Odyssey dataclasses/enums into JSON-compatible values.
Do not serialize arbitrary Python objects, exception objects, provider responses, or `repr()` output.

Persist bounded error/reason strings already exposed by the application result rather than stack traces.

## Lifecycle

Phase 17B initially creates **open** pending records and makes them inspectable.

Resolution, dismissal, reopening, replacement of temporary source links, interactive clarification, and
retry execution belong to a later HITL contract. Do not invent those workflows merely because the file
format could support them.

In particular, Phase 17B does **not** modify a source note to point at a pending artifact. Phase 17A now
withholds unsafe dependent mutations entirely, so introducing temporary graph proxies would add a second
behavior without a demonstrated need.

## Failure and crash semantics

- Successful Phase 17A note writes remain successful if pending-state persistence later fails.
- The pending durability failure must be explicit in `ApplicationResult`.
- Existing revision/schema/identity guards remain authoritative for note mutations.
- Pending records are create-only in the initial phase; duplicate request IDs fail closed rather than
  overwriting prior evidence.
- Full process-crash recovery between a successful knowledge write and the final pending-record write is
  deferred to Phase 19 hardening. Phase 17B does not introduce transactions or a journal/WAL.

## Model policy and deterministic testing

Phase 17B changes no production LLM prompt, Structured Outputs schema, writer contract, or model
selection.

Normal tests use deterministic plans/results and filesystem fixtures. They make **zero live Sol/Luna or
other OpenAI calls**. No new live benchmark is required unless implementation unexpectedly changes a
production model-facing contract; if that becomes necessary, stop and treat it as a separate reviewed
change under `AGENTS.md`.

## Acceptance criteria

Phase 17B is complete when deterministic tests prove at least:

1. a fully completed request creates no pending record;
2. an incomplete validated request creates exactly one record using the original `request_id`;
3. the record preserves the exact user request, planner limitations, application status, affected
   successful IDs, validated incomplete action snapshot, and matching typed result evidence;
4. multiple unresolved dependencies from one unit survive round-trip without being collapsed;
5. a failed CREATE dependency plus an independent successful mutation yields one pending record that
   preserves both the failure/deferred evidence and the successful affected ID;
6. partial bulk UPDATE evidence preserves selected/succeeded/failed stable IDs without rerunning
   selection;
7. delegated work is persisted as pending without being routed or executed;
8. planner failure before a valid `RequestPlan` produces no pending record;
9. a missing/failing pending store is surfaced in the application result and does not roll back prior
   successful note writes;
10. pending records round-trip deterministically from an isolated state directory;
11. duplicate record creation fails closed rather than overwriting;
12. canonical schema, `VaultRepository`, normal context indexing/resolution, and bulk membership remain
    unchanged and unaware of pending records;
13. the full deterministic test suite runs without network access, OpenAI credentials, or model token
    spend.

## Out of scope

- adding a canonical pending-work note type;
- storing pending JSON/Markdown inside ordinary knowledge scans;
- semantically indexing pending state;
- automatic HITL prompts or Telegram/n8n notifications;
- choosing between ambiguous candidates;
- automatically retrying pending work;
- replaying saved actions without current safety checks;
- resolving/dismissing/reopening lifecycle mutations;
- temporary pending wikilinks in canonical notes;
- Git commits or request-level Git history (Phase 17C);
- semantic history of every user request;
- operational tracing/log aggregation;
- transactions, rollback, WAL, or crash-consistent request journaling;
- databases or new services.

## Open decisions

- **None.** The approved `/data/odyssey/state/pending/` boundary and deterministic JSON representation
  are implemented. Do not broaden later work unless repository evidence reveals a new material
  ambiguity.
