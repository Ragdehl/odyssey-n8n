---
name: odyssey-generality
description: Review semantic fixes, new Apps, Router, Temporal, Core, identity and E3 changes for reusable general contracts. Use before modifying shared interpretation or validating future capabilities.
---

# Odyssey generalization before special cases

Read `docs/architecture/application-extensibility-plan.md`, `router-hybrid-interpretation-contract.md` and relevant E2/E3 contracts; verify the implemented branch. Decide whether a failure is semantic, transport/contract, local executor or UI diagnostic **before editing**.

- Never branch on example names, text, pronouns, language, punctuation, IDs, fixed counts of people/tasks/candidates or corpus examples. Extract the general missing invariant; test all affected consumers.
- Router hypotheses must preserve exact original spans. A source candidate can produce 0, 1 or many Core facts; facts may combine candidates (N:M). Do not equate source/route ordinals with write ordinals; never silently truncate.
- Router and Temporal propose bounded evidence, not canonical identity or write permission. Apps own their specific lifecycle; Core owns identities, target selection, shared planning and E3 canonical mutation. A new App should extend registration/composition, not duplicate Core or proliferate `if capability ==...`.
- For a singular typed mention, Core may reuse or create a nonconflicting new identity; a verified `complete_set` can be literal if members unknown. Ambiguous, stale, partial or conflicting identities fail closed. Any material change to these human-approved semantics needs approval.
- Only introduce ports/abstractions for demonstrated duplication. Preserve checks at deliberate security boundaries, and avoid new infrastructure without concrete necessity.
- **Reuse-first inventory for new product features, especially user-editable schemas:** inspect the canonical `config/note-schema.json` and `scripts/validate_note_schema.py`; existing schema composition (`odyssey_core/schema_types.py`, application extensions), Notes capabilities/UI, query filters, shared Core/E3 prepared property mutation and Git readback, `PendingWorkRepository`/delivery receipts, background index refresh and bounded thread pools **before** proposing a new model, agent, queue, database, writer or UI framework. Reuse functionality only where the ownership contract actually fits; index refresh is not automatically a durable long-running backfill queue, and parallel interpretation must never grant parallel unsynchronized Git/Markdown writes. Identify the specific missing capability and its smallest justified addition. A model can propose changes and evidence; human confirmation plus deterministic schema validation and Core/E3 authorize application. Existing app-managed types must retain their separate lifecycle ownership.

Check adversarial shapes: 0/1/2/3/5+ candidates, one-to-many and many-to-one facts, app mixtures, N:M, implicit SELF, temporal co-reference, negation/condition/correction, unknown identity, concurrency, replay/idempotence and canonical readback. Reuse `tests/fixtures/full_message_corpus_v1/` with synthetic vaults. Frozen provider replay is not fresh live proof. At readiness use focused contracts + full cross-surface gate + scoped E2E.
