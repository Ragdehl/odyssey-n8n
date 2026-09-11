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

### Per-message cost cue

The conversational Odyssey surface may later show a small, optional estimated-cost cue directly on each Odyssey response bubble when request-level usage evidence and a valid dated pricing snapshot are available. A suitable presentation is a visually secondary value such as `€0.003` in a corner of the Odyssey message, without adding token/model detail to the normal chat view.

The displayed amount should represent the estimated cost attributable to the whole logical Odyssey request that produced that response, not just the final answerer call, so planner, resolver, answerer, fallback, and provider-retry costs are not silently omitted or double-counted. If cost cannot be calculated reliably, the cue should be absent or explicitly unavailable rather than shown as zero. Advanced drill-down may expose the per-stage/provider breakdown separately.

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

## Reference-first request trace

Odyssey should eventually be able to reconstruct one logical request from receipt through planning, semantic execution, canonical mutation, Git, derived-index refresh, and response using the existing `request_id` as the correlation key. This trace is diagnostic/history state, not a second copy of canonical knowledge.

The preferred design is **reference-first**. Do not duplicate note bodies, facts, or other canonical knowledge into a request-trace record merely to make inspection convenient. Where durable identifiers already exist, retain those identifiers and resolve the authoritative data on demand:

```text
request_id
   |
   +--> planner outcome / validated plan
   +--> action + unit outcomes
   +--> stable_note_id ----------> canonical Markdown
   +--> Git commit/request marker -> exact canonical diff/history
   +--> pending record ID --------> durable pending state
   +--> n8n execution reference --> integration execution details
   `--> operational evidence -----> stages / timing / usage / cost
```

A compact trace/index may therefore retain correlation and execution evidence such as timestamps, provider/model configuration, normalized usage/cost, stable stage/error codes, action kinds, operation outcomes, affected `stable_note_id` values, Git/request correlation, and references to other durable evidence. It should prefer links/identifiers over copied payloads whenever the referenced source is expected to remain available.

The **validated planner result** is an intentional exception to the no-duplication preference when no other durable authority already preserves it. It is valuable audit evidence because it captures the semantic boundary Odyssey actually accepted before acting. This is especially useful when diagnosing planner/schema failures. Persist only the validated planner result or a deterministic equivalent rendering; do not persist hidden reasoning, chain-of-thought, raw provider output, or rejected provider payloads merely for completeness. If planning fails before a validated result exists, bounded fields such as provider status, parse status, validation stage/code, attempt count, response ID, usage, and safe error category are sufficient diagnostic evidence.

This direction does **not** require an immediate new tracing database or one large file that copies everything. First determine which useful pieces are already durable in ApplicationResult, Git, pending state, n8n execution data, and existing operational evidence, then add only the smallest missing reference/index representation needed for convenient reconstruction and product drill-down.

This work is also **not a sequencing blocker** for continued Odyssey Online development. After the current planner hardening is complete, product progress, real-app use, and the already-preserved cost-aware Luna-first planner experiment may proceed before implementing a consolidated request-trace representation. Real usage should help determine which missing trace links are actually worth persisting.

## Deployment provenance and boundary-level diagnostics

The Phase 20.3 protected mobile E2E exposed a concrete observability gap: Core/runtime diagnostics were sufficient to prove that `qzxqzx` correctly produced `needs_attention + UNRECOGNIZED_REQUEST`, while the deployed n8n product workflow returned an ordinary empty-result response because the active workflow had drifted behind the version-controlled `workflows/odyssey-online.ts` contract.

This establishes a durable requirement: advanced request diagnostics must eventually cover not only model/Core stages, but also the **integration boundary and deployed artifact identity** that transformed the result.

A useful bounded trace should be able to show, when available:

```text
request_id
   |
   +--> planner outcome
   +--> runtime/ApplicationResult outcome
   +--> n8n product-routing outcome
   +--> grounded-answerer path / skipped
   `--> final browser product kind

Deployment provenance
   +--> repository commit / source revision
   +--> expected workflow source fingerprint
   +--> active n8n workflow ID
   +--> active n8n workflow version ID
   +--> deployment environment + deployed-at evidence
   `--> source/deployment match: MATCH | DRIFT | UNKNOWN
```

The exact fingerprint format is deferred, but the behavior is not: a deterministic deployment check should be able to compare the expected version-controlled workflow with the single active production workflow and report drift before or during E2E/deployment verification. This should not depend on manually exporting every workflow and visually locating the active copy.

The deployment path should also converge on a stable operational identity instead of accumulating ambiguous duplicate active endpoints. Historical inactive workflow copies may exist, but production verification must identify exactly one active workflow for a public product path and must fail closed or warn clearly when multiple active copies could compete for that path.

For the advanced per-request inspector, boundary-level status is as important as model telemetry. A future diagnostic could therefore make a mismatch obvious without showing unsafe internals:

```text
Planner          Luna / low       CLARIFY
Runtime          application      CLARIFY
n8n router                         EMPTY   ⚠
Answerer                           skipped

Deployment
source revision                    abc123
active workflow                    hMbt... / version e367...
source match                       DRIFT   ⚠
```

Ordinary users do not need this information in the chat. It belongs in authorized advanced diagnostics and deployment verification. Reuse existing Git/n8n/runtime evidence where possible; do not introduce a new observability service merely to calculate deployment provenance.

## Validation scenarios for the future

Before adopting the product surface, validate at least:

- an ordinary user can understand current spend without seeing distracting technical internals;
- an advanced user can inspect one request and reconstruct the bounded model/stage/usage path;
- multiple provider calls within one request remain distinguishable;
- a per-message cost cue, when enabled, represents the full logical request cost without double counting provider retries or omitting upstream planner/fallback cost;
- missing provider counters stay unavailable rather than becoming zero;
- cost is unavailable without a valid pricing snapshot;
- a historical calculation identifies the pricing snapshot used;
- monthly totals aggregate request-level evidence without double counting retries/provider calls;
- a month-end projection is clearly labelled and can be absent when insufficient evidence exists;
- boundary-level diagnostics can distinguish planner/runtime outcome from n8n routing/final product outcome;
- deployment verification can identify the active production workflow and deterministically report source/deployment drift or unknown provenance;
- duplicate workflow history cannot make production verification silently inspect the wrong active public endpoint;
- no prompts, hidden reasoning, credentials, unrestricted exceptions, or unrelated personal knowledge leak through the diagnostic view;
- any future multi-user view enforces authorization before detailed telemetry is returned.

## Deferred decisions

Decide from real Odyssey Online usage:

1. which metrics belong on the default user surface;
2. whether the per-message estimated-cost cue should be always visible, optional, or available only in an advanced mode;
3. the exact advanced/admin/developer presentation and access mechanism;
4. whether the existing n8n-retained operational results are sufficient for the desired history window or whether a small derived analytics store later earns its complexity;
5. the canonical attribution field for applications/capabilities once that execution boundary exists;
6. the billing/calendar period used for forecasts;
7. the simplest month-end projection that is useful without creating false precision;
8. whether provider invoice/billing data should ever be reconciled with Odyssey's request-level estimates;
9. the exact deterministic fingerprint/provenance contract that ties version-controlled workflow source to the active n8n deployment.

Do not introduce a new observability service, analytics database, telemetry vendor, or billing subsystem until the existing bounded request evidence is shown to be insufficient for an actual product requirement.
