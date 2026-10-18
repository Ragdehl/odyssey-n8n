# ChatGPT-authored microfeature: exact overlapping-literal provenance

## Scope
Fix one confirmed architectural defect in the Core-owned, domain-agnostic immutable provenance validator. Exact substring candidates that overlap in the original source must count as distinct occurrences. For example, source "aaa" contains "aa" at offsets 0 and 1 and must never be treated as uniquely anchored. Apply the same rule to the containing original context and to the literal inside that context. No grammar, language, Note type or Task-specific heuristic. Preserve existing literal and context behavior for genuinely unique spans.

## Acceptance criteria
- Generic `anchor_literal_evidence` does not accept an ambiguous overlapping primary or supporting source literal.
- Optional unique context can disambiguate a literal that repeats outside that context, but cannot hide overlap within it; ambiguous repeated contexts are still rejected.
- Existing evidence modes, N:M shared offsets and unrelated apps behave unchanged.
- Core rejects ambiguous evidence before calling semantic reviewers and before all Writer mutations; disposable runtime/vault readback confirms zero writes.
- Python focused and cross-surface suite stay green. Reviewer distinguishes this feature's diff from preexisting unrelated P4 design limitations.
- No DEV/PROD deploy, no public route edit, no secrets, no relaxing security checks, no historical benchmark tweaks.

## Developer
ChatGPT from the Odyssey discussion. Implementation is committed on the P4 feature branch. First review round should SKIP Codex Builder to avoid duplicate token consumption. Independent architecture, quality, semantic QA and performance reviewers see the exact Git diff and may fail if real new regressions exist. No unattended automatic repair permitted in this first pilot.
