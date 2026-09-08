# Planner incident hardening

Status: **deterministic implementation prepared; focused Sol/low live evidence pending**

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
character/byte lengths, parse status, result kind, and structural counts from a successfully
validated result. It stores no prompt, raw output, output prefix/suffix, exception body, or hidden
reasoning.

## Acceptance criteria

- `Bdbd`, `asdfgh`, and `???` are schema-valid as `CLARIFY` and execute no Odyssey action.
- Existing retrieval, write, and delegation plans remain valid under `PLAN`.
- Every production planner request carries the 4,096-token cap.
- The production planner client performs no automatic SDK retry and Core adds no retry loop.
- Incomplete/output-limit and transport failures return bounded failed evidence with no retrieval,
  mutation, pending record, or persistence side effect.
- Runtime and Odyssey Online can return deterministic clarification without an answerer call.
- Deterministic focused and full repository gates pass.
- Focused live evidence uses the exact production `gpt-5.6-sol` / low configuration before adoption.

## Focused live evidence gate

The frozen cases are in `benchmarks/planner_incident_hardening/cases.json`. They cover the historical
`Bdbd` sentinel, two additional nonsense inputs, normal retrieval, normal write, and legitimate
delegation. The runner requires an explicit live-confirmation flag and records bounded validated
results rather than raw provider responses.

**NOT RUN — awaiting human authorization.** Deterministic tests prove only that the schema,
validation, application, runtime, and product layers can handle the new outcome safely; they cannot
prove that Sol chooses `CLARIFY` for the sentinel inputs.

## Out of scope

- inferring the incident's unknown generation content or root cause;
- Luna-first planning, `PLAN | ESCALATE`, model comparison, or cost-aware routing;
- broad `maxItems` additions or ontology/note-schema changes;
- application-level retries, reproduction of the 128k output, or live provider calls in this change;
- Cloudflare, authentication, networking, real-vault, or unrelated Phase 20 changes.

## Open decisions

None for the deterministic checkpoint. Human authorization is required before the focused live gate.
