# Functional Roadmap

This is Odyssey's canonical intended **functional** phase sequence. It records what the product
should build next, rather than the process roadmap in
[Development Pipeline](development-pipeline.md). Git history and ADRs remain authoritative for
what was actually implemented. The roadmap may change, but a future change must update this file
explicitly rather than relying on agent or chat memory.

Status: ✅ **IMPLEMENTED** · ➡️ **NEXT** · ⬜ **PLANNED** · 💡 **CONDITIONAL / LATER**

## Established sequence

- ✅ **Phase 9 — deterministic exact entity resolution:** exact primary-name and alias evidence.
- ✅ **Phase 10 — semantic entity candidate retrieval:** local ranked candidate evidence only.
- ✅ **Phase 11 — contextual/hybrid existing-entity resolution:** Phase 11A established the
  direction; 11B.1 validated the model/prompt and 11B.2 delivered the production resolver with
  deterministic validation and evidence minimization.
- ✅ **Phase 12 — deterministic entity persistence:** explicit validated create and update
  operations.
- ✅ **Phase 13 — general knowledge context retrieval (`get_context`):** validated-plan retrieval
  over a rebuildable local context index.
- ✅ **Phase 14 — request interpretation / validated `RequestPlan`:** Sol/low turns a message into
  ordered retrieval and content-only create-intent actions without retrieval or persistence.

## Next functional phase

➡️ **Phase 15 — write planning / knowledge preparation**

Transform write intent into structured knowledge work without persisting it. This includes
knowledge decomposition, related knowledge units, facts, and references in a form suitable for
later deterministic validation and existing-entity resolution.

The opening architecture question is whether the **same Sol/low interpretation call** used by Phase
14 can produce retrieval planning and structured write/knowledge preparation in one `RequestPlan`
response. Phase 15 must test this preferred simplification; it must not assume a second LLM call is
needed and must not change the Phase 14 production contract as part of that investigation.

```text
user message
    |
    v
single Sol/low interpretation call
    |
    +--> RetrieveAction(s)
    |
    `--> structured write action / knowledge units
             |
             v
       deterministic validation
             |
             v
       existing entity resolution
             |
             v
       later persistence
```

This keeps one semantic interpretation boundary, avoids interpreting the same request twice, and
can reduce latency and cost.

## Remaining intended sequence

⬜ **Phase 16 — resolved knowledge persistence**

Use the existing Phase 11 resolver for references in prepared knowledge, then implement
`save_knowledge` to coordinate validated creates, updates, and canonical wikilinks. It must retain
ambiguous and unresolved outcomes rather than inventing identity or silently changing the ontology:
`UNRESOLVED != CREATE`. Failure to resolve an existing entity, or ambiguous resolution, authorizes
neither creation nor mutation; create/update must be explicit and validated before persistence.

⬜ **Phase 17 — executable application flow and stable application boundary**

Compose validated `RequestPlan` actions into a small executable Core application flow: retrieve
context where requested, prepare and save knowledge where approved, and return a stable
application/API result. This is a narrow composition boundary, not a generic workflow engine,
router, DAG, or new service.

⬜ **Phase 18 — n8n integration and first end-to-end Odyssey use case**

Expose the stable application boundary through n8n orchestration and verify one real, bounded
end-to-end Odyssey use case. n8n remains responsible for external integration, triggers, retries,
and observability; `odyssey_core` retains domain behavior.

⬜ **Phase 19 — end-to-end hardening**

Harden the proven flow with repeatable integration and failure-path evidence, idempotency and
operational behavior appropriate to the demonstrated use case. Do not broaden the architecture
without evidence.

## Conditional later work

- 💡 **Human-in-the-loop:** add a minimal clarification or approval path only if demonstrated
  ambiguity, safety, or user-control needs require it.
- 💡 **Performance and index optimization:** optimize retrieval or indexes only when measurements
  show that current local, rebuildable approaches are inadequate.
- 💡 **Proactive Memory/Context Layer:** consider non-disruptive resurfacing only after the direct
  end-to-end flow proves useful; it remains a later product capability.

Phase 16 deliberately combines prepared-reference resolution and persistence because the latter
requires the former's resolved identities and canonical links. Phase 17 keeps Core composition and
its stable boundary together; Phase 18 then proves that boundary through the distinct n8n
integration responsibility. These combinations avoid ceremonial micro-phases while preserving
testable functional boundaries.
