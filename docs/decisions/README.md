# Architecture Decisions

This directory is reserved for Architecture Decision Records (ADRs) covering significant choices that affect system structure, long-term contracts, security, data ownership, or multiple workflows.

Routine implementation details and easily reversible node configuration do not need an ADR. Those belong in workflow documentation or code comments where necessary. Git history, Pull Requests, and tests track implementation state.

When an ADR adds real value, it should state the context, decision, alternatives considered, consequences, and status. Use a numbered descriptive filename such as `0001-example-decision.md`. Avoid creating records solely for documentation ceremony.

## Decision history

- [0000: Foundational knowledge and application boundaries](0000-foundational-architecture.md)
- [0001: Phase 10 semantic candidate retrieval](0001-phase-10-semantic-candidate-retrieval.md)
- [0002: Phase 11A contextual-resolution benchmark](0002-phase-11a-contextual-resolution-benchmark.md)
- [0003: Phase 11B.1 OpenAI contextual-reasoner validation](0003-phase-11b1-openai-model-validation.md)
- [0004: Phase 11B.2 production contextual resolution and evidence minimization](0004-phase-11b2-production-resolution.md)
- [0005: Phase 12 entity persistence](0005-phase-12-entity-persistence.md)
- [0006: Phase 13 separate general knowledge context retrieval](0006-phase-13-context-retrieval.md)
- [0007: Phase 14 request planning boundary](0007-phase-14-request-planning.md)
- [0008: Phase 14 v3 planner tag interpretation](0008-phase-14-v3-planner-tags.md)
- [0009: Phase 15 semantic write-planning boundary](0009-phase-15-semantic-write-planning.md)
