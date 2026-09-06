# Future Odyssey product usage observability

Status: **preserved product direction; implementation deferred until the Odyssey Online product surface can use real request evidence**

## Product goal

Odyssey should make AI usage and cost understandable without turning the normal product into a developer console.

The product should preserve two separate concerns:

1. collect only bounded, safe operational and usage evidence that is genuinely useful;
2. decide how much of that already-available evidence each product surface should expose.

The default user experience should remain simple. Advanced users, administrators, and developers should be able to inspect substantially more detail from the Odyssey application when that helps diagnose behavior or understand cost.

```text
request execution
      |
      v
bounded operational / usage evidence
      |
      v
safe product projection
      |
      +--> SIMPLE USER VIEW
      |
      `--> ADVANCED / ADMIN / DEVELOPER VIEW
```

This is primarily a presentation and access-boundary problem, not a reason to create a second observability system.

## Reuse existing Odyssey evidence

Phase 19.2 already added bounded request-level operational evidence under the existing `request_id`, including total duration, ordered stages, safe model/reasoning identity where available, provider-call boundaries, supplied token counters, and safe outcome/error categories.

Phase 20.1A also provides provider-neutral usage extraction and cost aggregation helpers for the answerer benchmark. Phase 20.1B is expected to add a dated verified pricing snapshot for comparable live evidence.

A future product view should reuse these contracts where they fit instead of introducing a new tracing database, event stream, or analytics authority merely to draw graphs.

Important existing safety boundaries remain in force. Product observability must not expose or retain for this purpose:

- hidden chain-of-thought or private model reasoning;
- credentials or provider secrets;
- raw provider responses merely for debugging convenience;
- unrestricted exception text;
- prompts, note bodies, or user content merely because a request is being measured;
- fabricated zero token/cost values when a provider did not supply enough evidence.

`request_id` remains the normal correlation key unless later evidence demonstrates a concrete need for another identifier.

## Simple default user view

For ordinary users, the UI should favor comprehension over exhaustiveness.

A useful default may expose only a small number of product-level signals, for example:

```text
SEPTEMBER
-------------------------
Estimated spend     €2.40
Requests               84
Month-end estimate   €6.10
```

Exact fields should be chosen from real usage. The default screen should not require users to understand token accounting, reasoning effort, internal execution stages, provider call structure, or model-routing details.

The normal product may offer a compact optional drill-down, but advanced diagnostics should not crowd the primary interaction surface.

## Advanced / admin / developer view

A protected advanced surface should expose the maximum **useful and safe** detail already available from Odyssey's bounded contracts rather than an unlimited dump of internals.

Where evidence exists, this can include:

- `request_id` and request timestamp/correlation information;
- model and reasoning configuration used at each provider-bearing boundary;
- input, output, reasoning, cached, or other allowlisted token counters when actually supplied;
- request and stage durations;
- stage outcomes and safe error categories;
- individual provider-call records when one logical request performs several calls;
- estimated request cost when backed by a dated verified pricing snapshot;
- aggregation by model, capability/application, request class, and time period when those dimensions exist safely;
- totals and trends over day/week/month;
- charts derived from those aggregates;
- a clearly labelled month-end cost projection when enough dated observations exist.

The advanced view is still a product projection, not authorization to reveal hidden model reasoning, raw prompts, secrets, unrestricted logs, or personal knowledge unrelated to the requested diagnostic.

## Cost estimation and month-end projection

Cost must remain evidence-based.

```text
provider usage counters
        +
verified dated pricing snapshot
        |
        v
estimated request cost
        |
        +--> daily/monthly aggregation
        |
        `--> month-end projection
```

Rules for the first implementation:

- keep raw usage counters distinct from prices so a later pricing change does not rewrite historical token evidence;
- label calculated cost as estimated unless it is reconciled against a provider invoice/billing source;
- preserve `unavailable` when the necessary usage or pricing data is missing;
- record the pricing snapshot date/source used for a calculation rather than silently applying today's price to historical evidence;
- make the month-end forecast explicitly predictive, not a billing guarantee;
- start with a simple transparent projection from observed spend rate and only add more sophisticated forecasting if real usage demonstrates a need;
- do not invent a separate long-lived analytics database until retained Odyssey/n8n evidence proves insufficient for the product requirement.

A simple first forecast could extrapolate the observed cost in the current billing/calendar period to its end. Irregular usage may make that estimate noisy, so the UI should communicate the approximation rather than imply precision.

## Capability / application attribution

When Odyssey applications become executable, usage should be attributable to a stable capability/application boundary when that identity is already known safely.

This supports questions such as:

```text
Which capability is using the most model spend?
How much does Odyssey Help cost compared with ordinary knowledge questions?
Did a request invoke Luna only, or Luna plus a stronger fallback?
```

Do not add arbitrary tags or duplicate request identities solely for analytics. Reuse stable application/capability identity from the execution contract once it exists.

## Access and product roles

The conceptual distinction is:

```text
ordinary user
    -> simple usage/cost surface

advanced user / admin / developer
    -> detailed bounded diagnostic surface
```

The exact permission model is intentionally deferred. The first single-user Odyssey Online MVP does not need a speculative role/ACL system merely to preserve this direction. When multi-user authorization exists, advanced diagnostics must respect the same privacy and authorization boundaries as the underlying requests.

A user must never gain visibility into another user's private request evidence simply because a detailed observability view exists.

## Validation scenarios for the future

Before adopting the product surface, validate at least:

- an ordinary user can understand current spend without seeing distracting technical internals;
- an advanced user can inspect one request and reconstruct the bounded model/stage/usage path;
- multiple provider calls within one request remain distinguishable;
- missing provider counters stay unavailable rather than becoming zero;
- cost is unavailable without a valid pricing snapshot;
- a historical calculation identifies the pricing snapshot used;
- monthly totals aggregate request-level evidence without double counting retries/provider calls;
- a month-end projection is clearly labelled and can be absent when insufficient evidence exists;
- no prompts, hidden reasoning, credentials, unrestricted exceptions, or unrelated personal knowledge leak through the diagnostic view;
- any future multi-user view enforces authorization before detailed telemetry is returned.

## Deferred decisions

Decide from real Odyssey Online usage:

1. which metrics belong on the default user surface;
2. the exact advanced/admin/developer presentation and access mechanism;
3. whether the existing n8n-retained operational results are sufficient for the desired history window or whether a small derived analytics store later earns its complexity;
4. the canonical attribution field for applications/capabilities once that execution boundary exists;
5. the billing/calendar period used for forecasts;
6. the simplest month-end projection that is useful without creating false precision;
7. whether provider invoice/billing data should ever be reconciled with Odyssey's request-level estimates.

Do not introduce a new observability service, analytics database, telemetry vendor, or billing subsystem until the existing bounded request evidence is shown to be insufficient for an actual product requirement.
