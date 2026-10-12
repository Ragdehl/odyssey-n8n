# 0010 — Interpret semantically dependent Router candidates as groups

- **Date:** 2026-10-12
- **Status:** **Accepted as target architecture** by the human. **Not implemented or activated** in DEV/PROD.
- **Normative detail:** [Router hybrid interpretation contract](../architecture/router-hybrid-interpretation-contract.md).

## Context

The strict interpretation of 2026-10-11 split messages into separately executed Core fragments even when an omitted subject, shared verb or postposed time was linguistically owned by adjacent facts. Safe source/identity/temporal carriers were introduced to reconstruct relationships across those calls. This reduced unrelated-message contamination, but multiplied provider calls and handoff complexity for intrinsically interdependent statements.

A 27-case design corpus suggested grouping compatible linguistic dependencies while retaining atomic candidate accounting. A five-case pilot on the existing Core with saved real Router proposals and real Temporal/Core/reviewer models yielded 2 fully written and readback-verified successes (F04, F16), 2 Core pending groups (F03, F23) and 1 unresolved Temporal shared clock (F21). The latter three require validator/temporal improvements and **are not counted as passing**.

## Decision

**Separate atomic candidate extraction from downstream group interpretation.** The Router identifies source-anchored candidates; a bounded compiler groups semantically interdependent candidates into exact-source interpretation groups. Each group goes once to Temporal when needed and to the ordinary Core Planner, which can plan multiple individual facts and destinations. Independent candidate coverage, pending reasons and canonical Writer/readback stay per fact, not per group. Keep independent source actions as separate groups even within a single sentence. Transfer evidence only **between groups** when verified by Temporal/Core; linguistic context already present inside one group must not require an earlier persistence roundtrip.

The original whole message is Router input and read-only provenance only; **it is not re-sent to Core for planning unrelated sibling groups**. No second semantic planner, identity authority, event store, database, workflow or schema is approved. Core remains GPT-5.6 for this phase; preserve GPT-6 Router/Temporal roles and defer model migration.

## Rejected alternatives

- **Strict one Core call per atomic candidate:** simple failure isolation but unnecessary handoffs and redundant provider calls for F04/F16/F23; remains a safe reference/fallback for independent work.
- **One Core request for every complete user message:** easy linguistic context but mixes unrelated shopping, people, Task and date claims and obscures independent safety/partial completion.
- **Merge all same-entity or same-day claims:** not sufficiently semantic, e.g. F06 (seeing Ana, buying bread) or F22 separate tasks. Shared context does not imply one interpretation group.

## Consequences / implementation gate

Requires a grouped source compiler, proof of per-candidate and per-fact N:M coverage, shared date/time ownership and preservation of safe partial writes. Preserve experimental split-route proof as a cross-group fallback; do not delete tests or reinterpret historical receipts. Repair F03 group identity, F21 shared postposed clock and F23 grouped-reference validation before production readiness. Run 27-case deterministic corpus and focused fresh model gates on synthetic Notes. Audit and explicitly supersede contradictory instructions before code work.

This ADR **records the agreed design direction, not a deployed runtime capability**. Only a separately validated change/merge/deployment can activate it.
