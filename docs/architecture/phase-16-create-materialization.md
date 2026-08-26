# Phase 16.6 CREATE materialization

Status: **contract defined; implementation pending**

This document is the canonical Phase 16.6 contract. It completes the per-note CREATE slice after
Phase 16.5 has already decided target identity/path and rendered safe reference occurrences. It does
not introduce RequestPlan orchestration or remaining Phase 16 mutation semantics.

## Objective

Turn one already-authorized CREATE `KnowledgeUnit` into one complete canonical Markdown note and
persist it exactly once.

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
        +--> invalid/incomplete schema state -> fail before writer
        |
        +--> no free-text facts -> empty body, no writer
        |
        `--> free-text facts -> Luna / medium -> one CREATE_BODY
                                      |
                                      v
                         Core validates body + links
                                      |
                                      v
                           Phase 12 create_entity()
                                      |
                                      v
                              one CREATED result
```

The real problem is not identity resolution, path allocation, or general orchestration: those are
already owned elsewhere. Phase 16.6 owns only the missing composition from an approved CREATE target
to one validated persisted note.

## Preconditions and responsibility boundary

Phase 16.6 consumes decisions already made by earlier phases. It must not repeat them.

The CREATE materializer accepts one validated `KnowledgeUnit` together with its matching
`UnitTargetPreflight` and, when references exist, the Phase 16.5C `rendered_facts` for that unit.

It requires:

- `unit.intent == record`;
- a non-null canonical target `type`;
- preflight outcome `CREATE`;
- matching ordered unit identity;
- preallocated `stable_id`, canonical human-readable `name`, and vault-relative `.md` path;
- safely rendered facts when the unit contains reference markers.

It does **not**:

- resolve identity again;
- decide CREATE versus UPDATE;
- allocate another ID or path;
- reinterpret the raw user request;
- mutate lifecycle metadata directly;
- access a semantic index for writing;
- run MiniLM/NLI writer gates;
- choose a different writer model;
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
deterministically to that empty state. Planner/contract-incompatible mutations must fail closed rather
than being silently reinterpreted.

A CREATE whose final metadata cannot satisfy the active canonical schema must fail before persistence.
Where the invalidity is already deterministically knowable before body generation — especially a
missing required type property such as `journal_entry.entry_date` — fail before any paid writer call.

No type-specific creation permission rules are added.

## Body generation

### No free-text facts

If the safely prepared fact tuple is empty, Phase 16.6 does not call a model. The canonical body is the
empty string.

This deliberately supports:

- structured-only CREATEs whose knowledge is fully represented in canonical properties/tags;
- the already-approved reference-only unit case, which may create an identity note so another
  pre-bound wikilink has a canonical target.

Final schema validation still applies. An empty body does not excuse missing required metadata.

### Free-text facts

When free-text facts remain, use the already-selected writer policy:

```text
model              gpt-5.6-luna
reasoning effort   medium
mode               CREATE
storage            false
output             exactly one CREATE_BODY
```

The request contains only the already-decided canonical note identity/type and the prepared facts. It
contains no existing body because CREATE has no authoritative previous body.

The writer may organize the supplied facts into concise readable Markdown, but it must not:

- add metadata or lifecycle fields;
- invent facts, dates, URLs, identities, aliases, or relationships;
- invent a proper name for an unnamed/contextual entity;
- turn a reflection, possibility, or uncertainty into an objective fact or commitment;
- resolve references or alter Core-bound link identity;
- emit another operation family.

For CREATE, valid writer output is exactly one `CREATE_BODY` with one string `content` value. UPDATE
operations (`NO_CHANGE`, `APPEND`, `REPLACE`, `REMOVE`, `INSERT_AFTER`) are invalid in CREATE mode.
A non-empty input fact set cannot produce blank body content.

## Reference safety

Phase 16.5C remains the only owner of wikilink target binding.

When prepared CREATE facts contain Core-bound wikilinks:

- every required bound `[[path|mention]]` occurrence must survive in the generated body;
- the writer may not invent an additional complete wikilink;
- the writer may not change a target path or display mention;
- raw `{{ref:N}}` markers are never accepted by the CREATE writer boundary.

Unresolved/ambiguous references remain plain human-readable mentions plus the existing explicit
`PendingReference` result produced before this phase. Phase 16.6 does not create HITL artifacts or
retry reference resolution.

Core can validate link preservation and output structure deterministically. Semantic faithfulness of
ordinary natural-language facts remains a model-quality property and therefore requires focused live
evidence whenever the production CREATE prompt materially changes.

## Type-aware writing guidance decision

Phase 16.6 does **not** introduce a type-writing-profile/skill system.

The existing Phase 16.3 corpus already exercised fifteen CREATE_BODY cases across multiple note
semantics with one generic bounded writer contract. That is sufficient evidence to start with the
simpler shared policy. A profile system would add another representation and maintenance boundary
without a demonstrated failure it solves.

If focused Phase 16.6 evidence later shows a concrete type whose body is materially poor without
specialized guidance, add the smallest schema-linked guidance mechanism then. This decision does not
freeze generic formatting forever.

## Persistence

After deterministic metadata and the complete body have both validated, call Phase 12
`create_entity()` exactly once using the **preallocated** stable ID and path.

The persistence boundary remains authoritative for:

- duplicate stable-ID rejection;
- canonical note-schema validation;
- lifecycle metadata;
- safe create-without-overwrite storage behavior.

A provider failure, writer-output failure, schema failure, ID collision, path collision, or storage
failure must produce zero partial note writes from this materialization call.

Phase 16.6 does not invent a transaction/orchestration framework around several CREATE/UPDATE units.
Cross-unit dependency ordering and partial-success semantics remain Phase 16.7 work.

## Acceptance criteria

Deterministic tests must prove at least:

1. one preflight-authorized CREATE uses exactly its preallocated ID/path/name;
2. identity resolution and ID allocation are not rerun inside materialization;
3. property/tag-only CREATE persists once with no writer call;
4. reference-only CREATE may persist a schema-valid empty body with no writer call;
5. missing required CREATE metadata fails before writer and persistence;
6. several free-text facts produce one writer call and one `CREATE_BODY`;
7. contextual unnamed CREATE preserves its contextual canonical identity and does not invent a proper
   name;
8. CREATE with deterministic properties/tags plus free text commits them together in one
   `create_entity()` call;
9. malformed output, more than one operation, a non-CREATE operation, null/non-string content, or
   blank content for non-empty facts fails with zero persistence;
10. required Core-bound links survive exactly;
11. a dropped, altered, or invented wikilink fails with zero persistence;
12. raw reference markers cannot reach the writer;
13. duplicate preallocated stable ID or occupied path fails without overwriting an existing note;
14. provider failure produces a typed failure and zero persistence;
15. the resulting note is canonical schema-valid at revision 1 after the single Phase 12 create.

## Focused live evidence

This phase changes the production writer contract from UPDATE-only to CREATE-aware and must therefore
run focused live evidence with the selected production configuration before being considered
validated.

Do **not** rerun model selection. Keep the live set small and reuse representative frozen Phase 16.3
CREATE cases where useful. The focused set should cover approximately six calls:

- ordinary multi-fact named entity;
- contextual unnamed entity;
- journal/reflection uncertainty preservation;
- multiple facts with one or more already-bound wikilinks;
- repeated or multiple different bound wikilinks;
- no-link regression sentinel proving the writer does not invent links.

Use `gpt-5.6-luna`, reasoning `medium`, `store=false`. Preserve exact requests, raw provider output,
deterministic validation, semantic adjudication, usage, and cost. Deterministic schema/failure tests
remain required but do not replace this live evidence.

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
- a type-writing-profile system without new evidence;
- new model selection or Luna low/medium routing;
- n8n integration.

Those remaining mutation/dependency semantics belong to Phase 16.7, and general execution composition
belongs to Phase 17.

## Open decisions

None required before implementation. Minor API/refactor choices should be resolved during
implementation without introducing a broader orchestration abstraction.

## Architecture challenge

**PROCEED.** The needed behavior is a small Core composition over capabilities Odyssey already owns:
Phase 16.5 preflight/binding, the selected Luna-medium writer, canonical note validation, and Phase 12
`create_entity()`. No new service, database, semantic routing layer, type-profile framework, or
workflow engine is justified. The main implementation risk is fail-closed CREATE validation, not
architecture.
