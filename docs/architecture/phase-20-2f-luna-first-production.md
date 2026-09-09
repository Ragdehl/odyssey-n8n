# Phase 20.2F — Luna-first production planning

Status: **implementation complete; planner-only live gate passed; deployment remains separate**.

## Objective

Adopt the validated Phase 20.2E Luna/low planner as the normal production first pass while preserving
the established Sol/low planner as a bounded fallback only when Luna fails closed structurally. Safe
Luna abstention must never grant Sol authority to guess missing user truth.

```text
request
  |
  v
Luna / low
  |
  +-- PLAN ------------------------> execute validated RequestPlan
  +-- CLARIFY ---------------------> ask user
  +-- ESCALATE --------------------> ask user
  +-- validated fail-closed error -> Sol / low once
                                      |
                                      +-- PLAN -> execute
                                      `-- CLARIFY -> ask user
```

## Acceptance criteria

1. Production runtime constructs the Luna-first planner by default.
2. The Luna provider prompt/schema is exactly the Phase 20.2E validated inherited-prompt boundary; no
   fresh simplified prompt is introduced.
3. A safe Luna PLAN or CLARIFY makes zero Sol calls.
4. A Luna ESCALATE makes zero Sol calls and becomes a non-executing user clarification.
5. A bounded Luna `RequestPlanningError` may trigger exactly one Sol/low fallback attempt.
6. Generic provider/network failures do not automatically double-call the same provider through Sol.
7. Automatic retries remain zero for both models.
8. Planner operational evidence preserves Luna and Sol fallback usage/model metadata as separate
   provider calls so future cost reporting does not misattribute tokens.
9. Focused deterministic tests, full CI, and SonarCloud are clean.
10. A minimal live production-shape gate confirms one normal Luna PLAN, one Luna abstention/clarification,
    and one forced fail-closed -> Sol fallback path without executing real-vault mutations.
11. Human approval remains required before deploying the merged runtime to the Raspberry production
    process; deployment must not alter Cloudflare, credentials, or vault contents.

## Architecture challenge

Result: **PROCEED**.

The experiment already proved the model/prompt boundary. Production adoption therefore needs only a
thin routing wrapper around the existing two validated planners. No router service, queue, LangGraph,
second application server, or duplicated semantic prompt is justified.

The safest initial interpretation of Luna `ESCALATE` is user clarification rather than Sol fallback.
Phase 20.2E's explicit escalation case lacked truth/authority that no stronger model could legitimately
invent. Sol fallback is reserved for fail-closed structured-result failure, where the historical Sol
planner can still provide a valid plan without changing user authority.

## Out of scope

- Replacing the contextual entity reasoner's Sol/medium model.
- Changing the grounded answerer (already Luna/none in production).
- Adding new clarification codes or changing the browser/n8n response contract.
- Cloudflare/Access deployment work from Phase 20.3.
- Real-vault mutation as benchmark evidence.
- Automatic model retries beyond the one explicit Luna -> Sol fail-closed fallback.

## Open decisions

None for the initial adoption gate. A future evidence-backed escalation reason may distinguish
"stronger model useful" from "user input required"; the current safe default is to ask the user.

## Planner-only live gate

The authorized production-shape gate completed with exactly two Luna API calls and one Sol API
call, all with zero automatic retries. Case A (`What do I know about Odyssey?`) returned a validated
direct Luna `RequestPlan` with one retrieve action and no Sol call. Case B used the exact missing-
authority sentinel and returned Luna `CLARIFY` as a non-executing user clarification with no Sol
call. Case C injected a synthetic local Luna `RequestPlanningError` (zero provider calls for the
synthetic first pass) and made exactly one real `gpt-5.6-sol` / low fallback call, which returned a
validated `RequestPlan` with one retrieve action.

The bounded evidence is retained in the gitignored
`benchmarks/.live-results/luna-first-production-20.2f-live.jsonl`. It contains only case IDs, route
and result-kind metadata, bounded provider status/model/reasoning/attempt/usage fields, and the
synthetic-failure marker; it contains no raw payloads, prompts, or hidden reasoning. The supplied
usage counters imply an estimated **$0.04541422** under the dated repository pricing snapshot;
cache-write counters were not supplied, so this is an estimate rather than an invoice total.

No Odyssey actions executed, no vault or pending-work state changed, and no deployment or production
routing change occurred. Raspberry deployment and any production activation remain separate human
review and authorization gates.
