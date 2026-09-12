# Future Extension Points

Status: **index of intentionally deferred product/architecture directions**.

This file prevents useful future requirements from disappearing into chats/issues without becoming a second copy of every future contract. Current implementation order belongs in the [Functional Roadmap](functional-roadmap.md).

## Dedicated future contracts

Use these documents as the detailed owners:

- [Odyssey Platform Direction](odyssey-platform-direction.md) — long-term Core/server/client/application boundary, user-owned storage, and local-first portability.
- [Multi-user Collaboration Direction](multi-user-collaboration-direction.md) — authentication/authorization, private/shared knowledge, groups, synchronization, and conflict safety.
- [Future user self-identity binding](future-user-self-identity.md) — bind each authenticated/current human to an ordinary canonical `person` note by stable note ID so first-person requests and applications can reuse the same knowledge without a profile silo or special `user` note type.
- [Future Odyssey help and conversation context](future-help-and-conversation-context.md) — isolated product-help retrieval plus bounded ephemeral follow-up context.
- [Future semantic request history](phase-17-request-records.md) — explicit history of what the user asked and what Odyssey did, correlated through `request_id`, isolated from canonical personal retrieval and operational tracing, and never hidden model reasoning.
- [Future product usage observability](future-product-usage-observability.md) — safe user/admin usage, timing, token, and cost projections from existing evidence.
- [Future Odyssey product interface](future-product-interface.md) — mobile-first chat feedback, note browsing/editing, activity/change visualization, and role-aware advanced surfaces.
- [Future capture-context provenance](future-capture-context-provenance.md) — optional request/fact capture location/context without confusing it with entity properties.
- [Future pending-reference evolution](future-pending-reference-evolution.md) — safe relinking, recurrence signals, and advisory schema-evolution evidence.
- [Future retrieval refinements](future-query-decomposed-retrieval.md) — query decomposition/entity coverage first, then measured candidate reduction/compact evidence if needed.

Real Odyssey Online use also preserves visual theming as a deferred interface direction. Iterate on presentation only after product usage warrants it; visual theming is not an architecture requirement. Detailed chat/note/activity/advanced-interface direction now belongs to [Future Odyssey product interface](future-product-interface.md) rather than being duplicated here.

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

## Pending work, HITL, and identity enrichment

- **Human-in-the-loop:** build on durable pending state when ambiguity, dependency failure, partial success, or explicit approval needs clarification. Do not add notification machinery solely to preserve the possibility.
- **Mention-to-alias promotion:** occurrence-local mentions are not aliases. Add semantic promotion only under a separate evidenced identity-safe contract; never promote arbitrary display wording automatically.
- **Derived identity/link graph:** aliases, wikilinks, and backlinks may be projected into rebuildable indexes when structural execution needs them. Markdown remains authoritative and semantic-first relationship retrieval stays the default for ordinary natural-language questions.
- **Derived identity/disambiguation health:** if useful, compute rebuildable indicators for notes that lack distinctive evidence instead of adding a canonical `incomplete` flag that can go stale. Such signals may support non-disruptive enrichment or resurfacing.
- **Future resolver context:** bounded recent conversation, active project/recent notes, or existing links may contribute evidence only after measured validation. None is current identity authority.

## Cost-aware request planning

Deterministic preparation is now active under
[Phase 20.2D](phase-20-2d-luna-first-planner-experiment.md). That document owns the frozen experiment,
historical evidence review, teaching/held-out split, and first live gate. This section retains the
longer-term adoption boundary; production remains on the established strong planner.

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

Do not rely only on Luna to recognize its own uncertainty. Historical benchmark failures may define narrow, deterministic **evidenced escalation guards** when Luna has previously produced a confidently wrong plan for a recognizable semantic pattern. A primary sentinel is event/fact time being incorrectly mapped to note metadata such as `created_at` or `updated_at`: for example, “purchases made in July” must not become “notes created in July” unless the user explicitly asks about note creation/update time. If Luna still proposes that unsafe mapping after prompt improvement, the request must escalate to the established strong planner even if Luna emitted `PLAN` rather than `ESCALATE`.

Such guards must come from reproducible benchmark evidence, not speculative complexity rules. Keep them few and removable: if later frozen evidence shows Luna handles a guarded pattern safely, the guard may be retired. The intended boundary is therefore:

```text
request
  |
  v
Luna -> PLAN / CLARIFY / ESCALATE
  |          |
  |          `--------------------------> strong planner
  v
known evidenced unsafe pattern?
  +--> yes -----------------------------> strong planner
  `--> no -> Core validates -> execute
```

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

## Feature challenge before extension

Every proposed feature should first be challenged against the architecture that already exists. The default assumption is **reuse before extension**: a new user-visible capability does not imply a new subsystem, application, note type, model stage, or infrastructure component.

Before adding architecture, ask in this order:

1. **Can Odyssey already do this with the current primitives?** Try to express the request as the existing generic `READ` / `WRITE` / `DelegateAction` model and current retrieval, grounded synthesis, identity, and mutation contracts.
2. **Can a small generic change unlock it?** Prefer a bounded planner/retrieval/configuration/contract improvement that helps many requests over a feature-specific branch.
3. **Can the user remain unaware of the mechanism?** The user should normally ask in natural language and should not need to choose an app, mode, retrieval strategy, model, note type, or workflow merely because the implementation is composed internally.
4. **Does the request truly need specialized executable semantics?** Introduce or delegate to an application/capability only when generic grounded retrieval/synthesis is insufficient because the operation needs domain-specific lifecycle/state, deterministic calculations, specialized mutation rules, permissions, external side effects/integrations, or persistent workflow state.
5. **Does new infrastructure have measured justification?** A new service, database, model stage, framework, or long-lived component is the last resort and requires concrete evidence that the simpler path cannot satisfy the real use case.

Preferred escalation order:

```text
already supported behavior
        |
        v
small configuration / prompt / contract change
        |
        v
small generic Core capability
        |
        v
registered app / DelegateAction
        |
        v
new infrastructure only with measured need
```

This applies especially when a feature sounds novel but is actually a composition of existing abilities. Cross-note comparison, recommendation, matching, or inference should first be tested as multiple bounded retrievals plus grounded synthesis rather than being promoted automatically into a new application. New abstractions should earn their existence through a concrete failure of the simpler architecture.

## General rule

Progressive disclosure applies to both product and architecture: keep the current Core small, load domain instructions only when the corresponding capability is selected, and add model/infrastructure/schema complexity only after a measured need appears.
