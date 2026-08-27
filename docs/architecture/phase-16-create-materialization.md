# Phase 16.6 CREATE materialization

Status: **implemented; deterministic CREATE materialization accepted**

This document is the canonical Phase 16.6 contract. It completes the per-note CREATE slice after
Phase 16.5 has already decided target identity/path and rendered safe reference occurrences. It does
not introduce RequestPlan orchestration or remaining Phase 16 mutation semantics.

## Objective

Turn one already-authorized CREATE `KnowledgeUnit` into one complete canonical Markdown note and
persist it exactly once, using deterministic rendering by default.

```text
validated KnowledgeUnit
        +
Phase 16.5B CREATE preflight
        +
Phase 16.5C rendered facts
        |
        v
Core stages canonical metadata
        |
        +--> invalid/incomplete schema state -> fail
        |
        +--> no free-text facts -> empty body
        |
        `--> free-text facts
                |
                +--> no explicit writing skill -> deterministic body
                |
                `--> future explicit writing skill -> semantic rendering allowed by that skill
        |
        v
Core validates body + links + schema
        |
        v
Phase 12 create_entity() exactly once
```

The real problem is not identity resolution, path allocation, or prose generation. Identity and path
are already owned by Phase 16.5B, references are already bound by 16.5C, and the planner has already
prepared the facts. Phase 16.6 owns the smallest safe composition from an approved CREATE target to one
validated persisted note.

## Preconditions and responsibility boundary

The CREATE materializer accepts one validated `KnowledgeUnit` together with its matching
`UnitTargetPreflight` and, when references exist, the Phase 16.5C `rendered_facts` for that unit.

It requires:

- `unit.intent == record`;
- a non-null canonical target `type`;
- preflight outcome `CREATE`;
- matching ordered unit identity;
- preallocated `stable_id`, canonical human-readable `name`, and vault-relative `.md` path;
- safely rendered facts when the unit contains references.

It does **not**:

- resolve identity again;
- decide CREATE versus UPDATE;
- allocate another ID or path;
- reinterpret the raw user request;
- mutate lifecycle metadata directly;
- access a semantic index for writing;
- invoke MiniLM/NLI writer gates;
- invoke Luna merely because free-text facts exist;
- orchestrate several units/actions;
- persist pending-reference artifacts.

## Deterministic CREATE metadata

Core owns the complete domain metadata supplied to Phase 12.

At minimum:

```text
name = preflight.canonical_name
type = unit.target.type
properties = validated canonical PropertyChange values
tags = explicit controlled TagChange result
```

Lifecycle fields (`id`, timestamps, actors, revision, schema version) remain Phase 12
`create_entity()` responsibility. The preallocated stable ID is passed as `entity_id`; it is not
inserted into caller-owned metadata.

CREATE begins from no existing domain metadata. Valid planned property/tag mutations are applied
deterministically to that empty state. A canonical property never needs an LLM merely to be stored.
Planner/contract-incompatible mutations fail closed rather than being silently reinterpreted.

A CREATE whose final metadata cannot satisfy the active canonical schema must fail before persistence.
Where invalidity is deterministically knowable before body construction — especially a missing
required type property such as `journal_entry.entry_date` — fail before doing any semantic work.

No type-specific creation permission rules are added.

## Default body materialization

### No free-text facts

If the safely prepared fact tuple is empty, the canonical body is the empty string.

This supports:

- structured-only CREATEs whose knowledge is fully represented in canonical properties/tags;
- the approved reference-only unit case, where an identity note may exist solely so another bound
  wikilink has a canonical target.

Final schema validation still applies. An empty body does not excuse missing required metadata.

### Free-text facts without a writing skill

This is the **default Phase 16.6 path**.

The planner has already interpreted the user's knowledge into ordered facts, and CREATE has no
existing authoritative body that needs semantic reconciliation. Therefore Core does not pay an LLM to
rewrite those facts when no explicit type-aware writing skill exists.

Deterministic rendering is intentionally boring:

```text
body = prepared facts, in planner order, joined by a single newline
```

Rules:

- preserve each prepared fact exactly;
- preserve fact order;
- add no headings, bullets, checkboxes, summaries, inferred prose, or other presentation semantics;
- preserve every Core-bound wikilink exactly;
- invent no additional wikilinks;
- raw `{{ref:N}}` markers are invalid at this boundary.

Readability improvements that require semantic organization belong to an explicit writing skill, not
to hidden generic CREATE behavior.

## Writing skills and optional semantic rendering

Phase 16.6 does **not** introduce a writing-skill registry or activate a generic CREATE LLM writer.
There are currently no approved type-aware writing skills, so the implemented Phase 16.6 CREATE path
is deterministic.

A future type-aware writing skill may explicitly state that a note type benefits from semantic body
organization or formatting. Because the canonical type is already known, selecting such a skill must
be deterministic; it is not another classification problem.

Conceptually:

```text
canonical type
     |
     +--> no writing skill -> deterministic body
     |
     `--> explicit writing skill -> skill-defined semantic renderer
```

If a later writing skill uses an LLM, the selected safe baseline remains the already-evidenced
`gpt-5.6-luna` / medium policy unless new evidence justifies changing it. That future renderer must
still receive only already-decided identity/type/facts and must preserve Core-bound links.

The existing Phase 16.3 CREATE_BODY benchmark remains useful historical evidence that Luna-medium can
render several CREATE semantics safely. It does **not** justify paying Luna for every CREATE when no
writing skill requires semantic rendering.

## Reference safety

Phase 16.5C remains the only owner of wikilink target binding.

For deterministic CREATE rendering:

- every required bound `[[path|mention]]` occurrence survives byte-for-byte because prepared facts are
  copied exactly;
- no additional complete wikilink is created;
- no target path or display mention is changed;
- raw `{{ref:N}}` markers are rejected.

Unresolved/ambiguous references remain plain human-readable mentions plus the existing explicit
`PendingReference` result produced before this phase. Phase 16.6 does not create HITL artifacts or
retry reference resolution.

## Persistence

After deterministic metadata and the complete body validate, call Phase 12 `create_entity()` exactly
once using the **preallocated** stable ID and path.

The persistence boundary remains authoritative for:

- duplicate stable-ID rejection;
- canonical note-schema validation;
- lifecycle metadata;
- safe create-without-overwrite storage behavior.

A schema failure, ID collision, path collision, or storage failure must produce zero partial note writes
from this materialization call.

Phase 16.6 does not invent a transaction/orchestration framework around several CREATE/UPDATE units.
Cross-unit dependency ordering and partial-success semantics remain Phase 16.7 work.

## Acceptance criteria

Deterministic tests must prove at least:

1. one preflight-authorized CREATE uses exactly its preallocated ID/path/name;
2. identity resolution and ID allocation are not rerun inside materialization;
3. canonical properties are staged deterministically with no writer/model call;
4. explicit tags are staged deterministically with no writer/model call;
5. property/tag-only CREATE persists once with an empty body and no model call;
6. reference-only CREATE may persist a schema-valid empty body with no model call;
7. missing required CREATE metadata fails before persistence;
8. several free-text facts are copied exactly, in order, with deterministic newline separation;
9. contextual unnamed CREATE preserves its contextual canonical identity and does not invent a proper
   name;
10. structured properties/tags plus free text commit together in one `create_entity()` call;
11. required Core-bound links survive exactly;
12. raw reference markers cannot reach persistence;
13. duplicate preallocated stable ID or occupied path fails without overwriting an existing note;
14. no CREATE code path invokes the semantic writer while no explicit writing skill exists;
15. the resulting note is canonical schema-valid at revision 1 after the single Phase 12 create.

No live LLM benchmark is required for this default deterministic Phase 16.6 implementation because the
production CREATE path makes no model call. If a writing skill is later introduced and activates
semantic CREATE rendering, that change must bring its own focused live evidence rather than silently
reusing historical benchmark results.

## Out of scope

Phase 16.6 deliberately excludes:

- UPDATE behavior already delivered by Phase 16.4/16.5C;
- whole-note delete / soft-delete and inbound-link policy;
- type reassignment;
- bulk cardinality;
- multi-unit dependency ordering, rollback, or partial-success result semantics;
- RequestPlan orchestration / `save_knowledge` API design;
- durable pending-reference artifacts or HITL;
- alias promotion from mentions;
- inverse/mirrored relationship writes;
- graph traversal;
- implementing a writing-skill registry;
- generic CREATE LLM calls;
- new model selection or Luna low/medium routing;
- n8n integration.

Those remaining mutation/dependency semantics belong to Phase 16.7, and general execution composition
belongs to Phase 17.

## Open decisions

None required before implementation. Minor API/refactor choices should be resolved during
implementation without introducing a broader orchestration abstraction.

## Architecture challenge

**PROCEED.** The simplest solution is smaller than the earlier draft: Phase 16.5 already provides safe
identity/path/reference preparation and Phase 15 already provides ordered facts. CREATE has no existing
body to reconcile, so generic semantic rewriting is unnecessary. Deterministic rendering plus one
Phase 12 `create_entity()` call solves the current problem. Writing skills remain an explicit future
extension and may opt into semantic rendering only when a demonstrated presentation need justifies the
extra cost and complexity.
