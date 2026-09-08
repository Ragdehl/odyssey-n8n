# Planner incident hardening

Status: **deterministic hardening under review; first focused Sol/low live gate completed with bounded validation failures**

Phase 20.2B and PR #89 are complete. The original stacked PR #92 closed automatically when its
merged base branch was removed; the fresh PR from current `main` supersedes #92 implementation-wise
while preserving the closed PR and old branch as historical evidence.

## Objective

Bound the cost and side effects of one production planner invocation while giving uninterpretable
requests an explicit safe outcome. This responds to the September 8, 2026 incident without claiming
that the surviving evidence proves what the model generated or that `Bdbd` caused the abnormal
generation.

## Architecture challenge

Result: **PROCEED**.

The demonstrated gaps are local to the existing planner boundary: no abstention result, no explicit
output-token cap, hidden SDK retries, and insufficient bounded response metadata. The smallest safe
solution keeps the established Sol/low single-call planner and existing Core/runtime/n8n boundaries.
It does not add a router, tracing system, provider, service, or application retry loop.

## Contract

The production structured result is a closed envelope:

```text
PlannerResult
   +--> PLAN    -> existing validated RequestPlan
   `--> CLARIFY -> UNRECOGNIZED_REQUEST, with no plan
```

The wire shape keeps the discriminator beside nullable `actions`, `limitations`, and
`clarification_code` fields rather than adding another deeply nested schema level. `CLARIFY` is not
an empty plan and is not delegation. Core returns it as non-mutating
`needs_attention` evidence before retrieval, history, pending-work, or write execution. The product
boundary maps the allowlisted code to deterministic clarification text; model-generated prose never
becomes an instruction or user-facing response.

One production planner invocation uses `gpt-5.6-sol` with low reasoning, `max_output_tokens=4096`,
and an OpenAI client constructed with `max_retries=0`. The pinned OpenAI Python SDK is 3.3.1; its
default retry count is two, so the explicit planner-only override is material. A non-completed
provider response, including an output-limit result, is rejected before JSON parsing. Partial output
cannot reach Core execution.

The existing operational evidence adds only bounded metadata: attempt count, response ID, provider
status, incomplete reason, normalized usage including reasoning tokens when supplied, output text
character/byte lengths, parse status, result kind, structural counts from a successfully validated
result, and an allowlisted local validation stage/code when post-parse validation rejects a result.
It stores no prompt, raw output, output prefix/suffix, exception body, or hidden reasoning.

## Acceptance criteria

- `Bdbd`, `asdfgh`, and `???` are schema-valid as `CLARIFY` and execute no Odyssey action.
- Existing retrieval, write, delegation, and mixed retrieval/write plans remain valid under `PLAN`.
- A real-world event month such as purchases in July remains in the semantic query for the canonical
  `purchase` candidate type, does not become note-lifecycle `created_at` or `updated_at` filtering,
  and reports `unsupported_domain_date` because purchases have no deterministic domain-date field.
- Every production planner request carries the 4,096-token cap.
- The production planner client performs no automatic SDK retry and Core adds no retry loop.
- Incomplete/output-limit and transport failures return bounded failed evidence with no retrieval,
  mutation, pending record, or persistence side effect.
- Runtime and Odyssey Online can return deterministic clarification without an answerer call.
- Deterministic focused and full repository gates pass.
- Focused live evidence uses the exact production `gpt-5.6-sol` / low configuration before adoption.

## Focused live evidence gate

The frozen cases are in `benchmarks/planner_incident_hardening/cases.json`. They cover the historical
`Bdbd` sentinel, two additional nonsense inputs, normal retrieval, normal write, legitimate
delegation, the event-date versus note-lifecycle regression, and a legitimate mixed retrieval/write
request. The runner invokes only the planner, evaluates the returned plan without executing it,
requires an explicit live-confirmation flag, and records bounded validated results rather than raw
provider responses.

The first authorized run completed exactly once with eight planner calls, no automatic retries, and
no action execution or vault mutation. The retained bounded evidence includes the three successful
clarification cases and the event-date case; four cases reached completed JSON parsing but were
rejected by local validation (`normal_retrieval`, `normal_write`, `legitimate_delegation`, and
`legitimate_mixed`). Their raw provider payloads were not retained, so the exact historical
validation cause is unknown.

The local planner now retains only allowlisted validation stage/code diagnostics for that boundary.
A separate fixed four-case follow-up runner reuses the four unresolved IDs from the frozen registry,
writes only to its own exclusive gitignored evidence path, and cannot select the four previously
passed cases. Further live calls are **NOT YET AUTHORIZED** pending human review and separate
authorization of that follow-up gate.

## Out of scope

- inferring the incident's unknown generation content or root cause;
- Luna-first planning, `PLAN | ESCALATE`, model comparison, or cost-aware routing;
- broad `maxItems` additions or ontology/note-schema changes;
- application-level retries, reproduction of the 128k output, or live provider calls in this change;
- Cloudflare, authentication, networking, real-vault, or unrelated Phase 20 changes.

## Open decisions

None for the deterministic checkpoint. Human authorization is required before the focused live gate.
