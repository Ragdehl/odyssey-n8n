# ADR 0004: Phase 11B.2 production contextual resolution and evidence minimization

- Status: Accepted — Phase 11B.2 complete; pending human merge review
- Date: 2026-08-18

## Context

Phase 9 exact lookup and Phase 10 semantic retrieval are local, validated Core capabilities.
Phase 11B.1 established the OpenAI contextual reasoner contract, but there was not yet a
production orchestration boundary for deciding whether an already-extracted reference identifies
an existing note. This phase does not create or update notes; `UNRESOLVED` is not a create signal.

Issue #20 remains the future home for recall-first candidate reduction and `retrieval_summary`.
Neither is part of this phase.

## Decision

`resolve_existing_entity` owns the narrow composition:

```text
exact unique -> local RESOLVED
       |
       +-> otherwise -> semantic candidates
                         + ambiguous exact candidates
                         -> validated note evidence
                         -> one contextual call
                         -> deterministic Core validation
```

An ambiguous exact collision always contributes every colliding candidate, even when semantic
Top-N would otherwise omit one. Semantic rank and similarity are retrieval evidence only and are
never sent to the strong reasoner as identity confidence. The reasoner has identity authority only
within the supplied candidate set; Core remains authoritative for schema, outcome, nullability, and
candidate-ID validation. Provider failures remain exceptions and are not converted to `UNRESOLVED`;
there are no automatic retries.

The production resolver requires callers to choose `semantic_limit` explicitly. Phase 11B.1c showed
that Top-5 recall is not a safe implicit large-vault assumption, and no production candidate count
has been accepted. Candidate reduction remains deferred to issue #20.

The provider evidence boundary is deterministic and currently includes the canonical filename name,
aliases, type, subtype and other identity-relevant structured metadata, human-readable linked names,
and the note body. Wikilinks are rendered to display names only: vault-relative path components and
heading fragments are removed, while explicit visible aliases are preserved. The body remains because
relationships, negative evidence, and context-dependent facts can be identity-bearing; this phase
removes clearly unnecessary evidence rather than deleting useful evidence for a theoretical minimum
payload. It excludes `created_at`, `updated_at`,
`created_by`, `updated_by`, `revision`, `schema_version`, source hashes, filesystem/runtime data,
and semantic similarity/rank. No raw provider payload or response is persisted or returned.

The OpenAI boundary keeps Responses API, strict Structured Outputs, `store:false`, medium reasoning,
the configurable Sol model baseline, request-time `OPENAI_API_KEY` lookup, no payload logging, no
automatic retries, and prompt caching disabled by default. Explicit prompt caching remains an
opt-in transport feature consistent with ADR 0003.

## Privacy facts and limits

Current official OpenAI documentation states that API inputs and outputs are not used to train or
improve OpenAI models by default unless an organization explicitly opts in to data sharing. It also
states that default abuse-monitoring logs may retain customer content for up to 30 days, subject to
legal requirements. `store:false` controls Responses application state; it is not equivalent to
Zero Data Retention (ZDR). ZDR is a separately approved organization/project control, and its
endpoint eligibility and application-state behavior must be checked independently. Odyssey does not
claim that ZDR is enabled.

For Responses, the official data-controls documentation describes a 30-day application-state period
by default or when `store:true`; `store:false` must therefore not be described as a universal
retention guarantee. Prompt caching also has separate storage implications and remains off by
default here.

Sources consulted on 2026-08-18:

- [OpenAI API data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint)
- [OpenAI enterprise privacy](https://openai.com/enterprise-privacy/)
- [OpenAI business data privacy](https://openai.com/business-data/)

## Consequences

Exact unique and local-no-candidate references avoid contextual-provider disclosure entirely.
`CONTEXTUAL` results mean exactly one contextual reasoner call occurred; their `candidate_ids` are
exactly the IDs supplied to that call, while local results return no candidate IDs. Returned usage
metadata is strict-allowlisted to known operational counters and never carries arbitrary provider
strings or content. Other references disclose only the supplied resolution context and minimized
candidate evidence, never the full conversation, unrelated notes, or global user profile. The bounded
production-parity checkpoint below validates the provider boundary without establishing a general
large-vault retrieval guarantee.

## Bounded production-parity validation

The frozen synthetic Phase 11B.2 production-evidence checkpoint completed on 2026-08-18 using the
existing ten calibration cases and twelve selected evaluation cases. All twelve requests used
canonical synthetic notes routed through `build_provider_evidence`, the current production wording,
Sol with medium reasoning, strict Structured Outputs, `store:false`, and caching disabled. Results
were 12/12 correct, 7 `RESOLVED`, 3 `AMBIGUOUS`, 2 `UNRESOLVED`, zero clear false `RESOLVED`, and
zero invalid decisions. The measured cost was $0.226770 using the dated Phase 11B.1 standard-price
methodology, including cache-write tokens at 1.25x input pricing. The safe result is recorded in
[`phase11b2_sol_parity_12.json`](../../benchmarks/phase11b2_sol_parity_12.json).

This bounded checkpoint did not run the remaining 78 cases or a full 90-case rerun. It is accepted
as the Phase 11B.2 parity checkpoint; future candidate reduction and `retrieval_summary` remain in
issue #20, and Phase 12 remains next.
