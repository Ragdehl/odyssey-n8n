---
name: odyssey-llm-stage
description: Create, extend, tune or debug an Odyssey production LLM interpreter, prompt, JSON schema, model role or reviewer (Router, Temporal, Core Planner, Tasks, Events). Use for ANY model-facing contract change.
---

# Build a new LLM stage by inheriting proven work

**Do not start from a blank prompt.** Every model stage must justify its unique semantic responsibility, source authority, output contract and validation evidence.

1. Decide if a new LLM call is actually required. Prefer a deterministic validator or an existing shared stage where equivalent evidence already exists. New calls add latency, cost and a fallible boundary.
2. Locate the **closest accepted same-capability prompt, schema, parser, examples, provider wrapper, rejection conditions and tests**. Verify its accepted hash/model/effort and active code (feature-only checkpoints ≠ DEV). Use `odyssey_core/temporal_interpretation.py`, `domain_interpretation.py`, `source_boundary_review.py`, `odyssey_runtime/whole_source_model_contract.py`, `odyssey_apps/tasks/interpretation.py` and `odyssey_apps/events/{interpretation,provider}.py` as starting points.
3. Inherit the **strongest validated prompt**. Prepare a small diff and a list of protected instructions: exact source, negation, uncertainty, ellipsis, conditional/correction scope, actor and canonical links, multi-fact completeness, date ownership, safe refusal and isolation from sibling groups. Any removal requires justification plus regression sentinel.
4. Define bounded typed inputs/outputs and strict provider JSON schema; finite enums, `additionalProperties: false`, limits for context/tokens/timeouts, explicit abstain/pending/error states, provenance of quoted source, actor/context freshness and untrusted model content. Reject invalid, missing, unexpected or cross-scope evidence **before** using output.
5. Respect authority: Router suggests source groups; Temporal interprets dates; Apps interpret only domain intent/lifecycle; Core owns identity and plans; E3/Writer owns authorized Markdown mutation. An LLM must NEVER be its own write authority or bypass the existing guards.
6. Generalize: no special handling for test names, pronouns, phrases, fixed numbers of participants/actions or candidate indices. Preserve singular typed identity create vs complete-set literal/fail-closed human decision. Use `odyssey-generality` when shared boundaries change.
7. Optimize only after correctness: cheapest sufficiently capable **validated production** model, effort, finite retries, prompt tokens and measured cost. Keep independent coverage reviewers unless equivalent protections are proven. Codex developer model routing is a separate decision.
8. Verification order: schema/failure SDK-fake tests → frozen genuine provider replay (clearly labeled) → original-message/multi-app adversarial corpus → disposable-vault vertical Core readback → full cross-surface gate → **one scoped live test with the actual production model and reasoning** after explicit cost approval (`odyssey-live-provider`). Preserve accepted prompt/model/schema hashes; do not advance golden hash to silence CI.
9. In the handoff record: stage purpose and owner, reused baseline, I/O schema and trust boundaries, delta, chosen production model/effort/budget, error/abstention behavior, adversarial tests, measured evidence and known limits.

Contracts: `docs/architecture/router-hybrid-interpretation-contract.md`, `docs/architecture/e2-shared-context-contract.md`, `docs/architecture/application-extensibility-plan.md`, `docs/architecture/testing.md`. These are pointers, not claims that all past experiments are active.
