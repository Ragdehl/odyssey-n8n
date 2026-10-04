# Router / Temporal / Core focused regression gate v1

This matrix is a permanent regression sentinel for the active Router -> Temporal -> Core architecture. It intentionally includes the relational cases discussed during the TemporalAnchor follow-up: `Bea y mis hijos`, a qualified child, and `mi amigo del barrio que tiene un barco`, together with multiple dates, exact date-times, a Day-owned timed occurrence, and a date range.

## Frozen matrix

- 3 Router calls: GPT-6 Luna / medium
- 4 Temporal calls: GPT-6 Luna / low
- 7 Core semantic-write calls: GPT-5.6 Luna / low
- 14 calls maximum, zero retries, zero mutation authority
- matrix SHA-256: `02d7f053a346db249282484f5d3740c9f6b0ea17de11a0e5524f1894495126a9`

The combined authorization envelope was `$0.09019472` including the 10% regional multiplier, below the explicitly authorized `$0.10` ceiling.

## Consumed v1 live result

The one authorized run produced 14 provider attempts and an estimated regional cost of `$0.02028279`. Result: **11/14 passed**.

- Router: 3/3
- Temporal: 4/4
- Core: 4/7

Passing Core sentinels included exact date-time entity ownership, Day-owned exact time, the relational friend description, and the qualified-child case.

Three Core cases failed locally and made no mutation:

1. `C1-exact-dates-compound`: Luna represented the first dated clause but omitted the two later dated clauses. Core rejected the partial plan because two trusted Temporal evidence items were missing.
2. `C5-bea-children-date`: Luna emitted `mis hijos` as a `complete_set` identity part inside a fact. Core correctly rejected it because fact references are singular.
3. `C6-bea-children-datetime`: same model/schema mismatch as C5, with exact date-time evidence correctly present.

The retained artifact is under `results/` and records the source digest used for this consumed attempt. It must not be overwritten or retried as v1.

## Provider-free successor correction

Review identified one real model-facing contract mismatch: the provider schema allowed `complete_set` candidate scopes inside fact identity parts even though the deterministic compiler rejects them. The current contract now narrows fact identity-part candidate scopes to `one_member` while leaving `complete_set` available for genuine operation targets. Set-valued participant wording can therefore remain literal instead of being misrepresented as one note reference.

The Temporal handoff prompt now also states the already-enforced invariant explicitly: every supplied temporal evidence item is mandatory in a PLAN unless a matching date-only value is consumed by its Calendar Day target; otherwise the model must ESCALATE rather than return a partial plan.

After these corrections the full provider-free suite passes. Any successor live execution requires a new one-shot runner/version and fresh explicit authorization; this v1 evidence remains historical and immutable.
