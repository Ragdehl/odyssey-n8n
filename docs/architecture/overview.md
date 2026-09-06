# Odyssey Architecture Overview

This document describes the **current system shape and authority boundaries**. Historical phase contracts, model-selection evidence, and implementation experiments live in phase documents, ADRs, and benchmarks; they are not repeated here.

## System shape

```text
              external clients
        browser / assistant / app
                   |
                   v
          trusted integration
                  n8n
                   |
                   v
          thin host runtime
                   |
                   v
+-----------------------------------------+
|              odyssey_core/              |
|                                         |
| planning -> retrieval / write execution |
| identity -> validation -> persistence   |
+--------------------+--------------------+
                     |
        +------------+-------------+
        |            |             |
        v            v             v
 canonical       durable        rebuildable
 Markdown        app state      runtime state
 vault/          state/         runtime/
```

Odyssey Core owns semantics. n8n owns external integration/orchestration. The runtime is a thin internal HTTP adapter that exposes Core to n8n; it is not a second domain service. Clients receive bounded product contracts and never gain direct filesystem, SQLite, Git, pending-state, or provider-credential authority.

## Request lifecycle

One natural-language request can contain retrieval, writes, or both.

```text
request + request_id
       |
       v
validated RequestPlan
       |
       +-------------------------+
       |                         |
       v                         v
 RetrieveAction(s)           WriteAction(s)
       |                         |
       v                         v
 get_context              target/reference resolution
       |                         |
       |                  create/update/delete decision
       |                         |
       |                  bounded materialization
       |                         |
       +-------------+-----------+
                     |
                     v
             ApplicationResult
                     |
         +-----------+-----------+
         |                       |
         v                       v
  grounded evidence      mutation/result evidence
```

The planner interprets the request but does not open notes, decide identity, or persist files. Retrieval returns grounded knowledge evidence. Write execution separately resolves identity and validates mutation authority before persistence.

## Identity resolution

Identity uses layered evidence and preserves uncertainty:

```text
reference
   |
   v
exact canonical name / alias
   |
   +--> one safe match -----------------> RESOLVED
   |
   `--> none / collision
            |
            v
      local semantic candidates
            |
            v
      bounded contextual resolver
            |
       +----+----+
       |    |    |
       v    v    v
   RESOLVED AMBIGUOUS UNRESOLVED
            |
            v
    deterministic Core validation
```

Semantic rank is candidate evidence, never identity confidence. A contextual model may choose only from candidates supplied to it; Core validates IDs and output shape and fails closed on invalid/ambiguous evidence.

## Knowledge mutation

The canonical unit of identity is normally one Markdown note per logical entity. Ordinary knowledge inside that note is append-first and logically atomic.

```text
stable note identity
       |
       +--> sparse structured metadata/state
       |
       `--> append-first atomic facts
                + request-derived locator
                + human-visible capture chronology
                + exact duplicate suppression
                + targeted correction/removal
```

New true knowledge normally appends. A previously true fact is not erased merely because a later fact records a transition. Explicit correction/removal can target an existing fact safely. See [Odyssey Knowledge Model](knowledge-model-direction.md).

Write materialization distinguishes:

- deterministic structured/property/tag operations where the contract is exact;
- deterministic CREATE rendering for prepared atomic facts;
- bounded semantic reconciliation only where existing free-text context genuinely requires it;
- soft deletion rather than ordinary destructive file deletion;
- explicit `one | all_matching` cardinality for bulk mutation, with deterministic selection authority;
- type migration in place while preserving stable note identity and failing closed on information loss.

## Persistence and authority

```text
Git repository
  -> code + config/note-schema.json + docs + workflow definitions

/data/odyssey/vault
  -> authoritative personal Markdown

/data/odyssey/state
  -> durable non-knowledge application/workflow state
     (for example pending work)

/data/odyssey/runtime
  -> rebuildable indexes, caches, embeddings/projections
```

Markdown is authoritative for personal knowledge. Git history provides request-correlated audit/recovery for canonical mutations but is not the knowledge database. Pending work survives restarts without entering ordinary knowledge retrieval. Derived indexes may be rebuilt from canonical data/configuration.

See [Local Storage Boundary](storage.md).

## External orchestration and Odyssey Online

The current standalone product boundary is intentionally thin:

```text
phone browser
     |
     | HTTPS (protected before real personal use)
     v
Odyssey Online / n8n
     |
     +--> serve minimal web surface
     `--> POST {request, request_id}
                 |
                 v
          internal runtime
                 |
                 v
              Core
                 |
                 v
       bounded product result
```

For retrieval results that need conversational synthesis, n8n may invoke the selected bounded grounded answerer. Write-only acknowledgements, empty retrievals, and ordinary failures do not require another model call.

The browser does not hold provider credentials or semantic authority. It creates a safe delivery `request_id`, reuses that ID only for an explicit retry of the same submission, and renders the narrow returned result.

The exact current Phase 20 contract is [Odyssey Online MVP](phase-20-odyssey-online-mvp.md).

## Source code responsibility map

- `odyssey_core/` — reusable application/domain behavior.
- `odyssey_core/atomic_facts.py` — canonical atomic-fact parsing/rendering primitives.
- `config/note-schema.json` — exact note schema and planner-facing schema guidance.
- `workflows/` — version-controlled n8n orchestration/integration workflows.
- `odyssey_web/` — browser-only UI/client logic.
- `benchmarks/` — frozen evidence for model/retrieval decisions; never production authority.

## Architecture invariants

1. Markdown remains authoritative personal knowledge.
2. Stable identity is independent from current human-readable name and physical filename.
3. Retrieval evidence is not mutation authority.
4. Models operate within bounded validated contracts; deterministic Core keeps safety authority.
5. n8n integrates/orchestrates but does not duplicate Core semantics.
6. Derived state remains rebuildable; durable non-knowledge state remains isolated from the vault.
7. Real personal data, credentials, security boundaries, and destructive actions require explicit human control.
8. Add infrastructure only after a measured need appears.

Implementation status belongs in the [Functional Roadmap](functional-roadmap.md). Exact historical rationale remains in phase documents, [ADRs](../decisions/README.md), and benchmark records.
