# Future Extension Points

Status: **index of intentionally deferred product/architecture directions**.

This file prevents useful future requirements from disappearing into chats/issues without becoming a second copy of every future contract. Current implementation order belongs in the [Functional Roadmap](functional-roadmap.md).

## Dedicated future contracts

Use these documents as the detailed owners:

- [Odyssey Platform Direction](odyssey-platform-direction.md) — long-term Core/server/client/application boundary, user-owned storage, and local-first portability.
- [Multi-user Collaboration Direction](multi-user-collaboration-direction.md) — authentication/authorization, private/shared knowledge, groups, synchronization, and conflict safety.
- [Future Odyssey help and conversation context](future-help-and-conversation-context.md) — isolated product-help retrieval plus bounded ephemeral follow-up context.
- [Future product usage observability](future-product-usage-observability.md) — safe user/admin usage, timing, token, and cost projections from existing evidence.
- [Future capture-context provenance](future-capture-context-provenance.md) — optional request/fact capture location/context without confusing it with entity properties.
- [Future pending-reference evolution](future-pending-reference-evolution.md) — safe relinking, recurrence signals, and advisory schema-evolution evidence.
- [Future retrieval refinements](future-query-decomposed-retrieval.md) — query decomposition/entity coverage first, then measured candidate reduction/compact evidence if needed.

When one of those capabilities becomes active work, update its owner and the roadmap rather than copying its detailed design here.

## Application routing and composition

Odyssey should support domain applications/capabilities without loading every app contract into the top-level planner.

The existing planner can preserve `DelegateAction`; later routing should happen separately:

```text
DelegateAction
     |
     v
compact installed-capability candidates
     |
     v
cheap/local router or bounded inexpensive model if needed
     |
     +--> selected capability -> load only its detailed contract
     `--> NO_MATCH / ambiguity -> fail safely
```

The first executable application should define the smallest real routing/manifest contract. Do not build a plugin marketplace, generic package manager, or extra expensive reasoning stage in advance.

Capabilities may depend on reusable lower-level capabilities when that prevents duplication, for example `Projects -> Tasks -> Reminders`. Dependencies must eventually be explicit, non-circular, and unable to bypass Core mutation/authorization rules.

## Type-aware writing profiles

Deterministic rendering remains the default for prepared CREATE facts. A future note/application type may opt into a writing profile only when human-readable body organization materially benefits from semantic rendering.

```text
known canonical type
      |
      v
optional writing profile lookup
      |
      +--> none -> deterministic renderer
      `--> profile -> profile-governed semantic renderer
```

This is presentation guidance, not a second ontology. A profile must not invent schema fields, alter identity/creation authority, or bypass Core validation. Any model-backed profile needs focused evidence for its own contract.

## Tags remain generic

The current boundary is already simple and should not be re-expanded speculatively:

- Core stores/filter/mutates explicit free-form tag values;
- Core defines no semantic tag registry;
- ordinary wording does not automatically create tags;
- user/application policy owns vocabulary and inference when a future app explicitly chooses to implement it.

Lifecycle/security/domain state belongs in structured contracts when needed, not hidden tag conventions.

## Cost-aware request planning

Current planning keeps its established strong-model baseline. If real Odyssey Online usage shows planner cost is material, benchmark the simplest two-level optimization:

```text
request
  |
  v
Luna first pass
  +--> PLAN ------> Core validates
  `--> ESCALATE --> established strong planner -> Core validates
```

The critical metric is **unsafe non-escalation**: a materially wrong accepted Luna plan that should have escalated. Reuse historical Luna failure cases as mandatory evidence. Adopt only if final end-to-end quality matches the established baseline and measured total cost improves materially. Do not add a third model/heuristic router first.

## Direct Markdown edit ingestion

Direct Obsidian/filesystem editing is expected long term. A later boundary should:

```text
external Markdown change
      -> distinguish from Odyssey-originated write
      -> inspect/validate changed knowledge
      -> preserve user wording where possible
      -> refresh derived indexes
      -> audit accepted change through normal request/Git safeguards
```

Do not implement blind vault-wide rewrite/normalization or self-trigger loops.

## Structured analytics

Counts, sums, averages, grouping, and similar operations should run deterministically over rebuildable structured/index data after an LLM or planner has produced a validated query intent. Do not send an entire vault to a model to perform arithmetic.

## Proactive resurfacing

Odyssey may later surface old knowledge because of time, active context, a project, or related incoming knowledge. It should be low-friction and non-disruptive, with real usage evidence determining which triggers are useful. Do not add notification infrastructure merely to preserve the idea.

## General rule

Progressive disclosure applies to both product and architecture: keep the current Core small, load domain instructions only when the corresponding capability is selected, and add model/infrastructure/schema complexity only after a measured need appears.
