# Functional Roadmap

This roadmap tracks current implementation status and near-term sequencing. Detailed phase evidence belongs in phase documents and ADRs rather than being duplicated here.

## Current Phase 20.3 status

```text
20.3A deployment/security inventory                          ✅ complete
20.3B protected hostname + Access + tunnel JWT enforcement   ✅ complete
      exact Odyssey-path bypass closure on n8n hostname      ✅ complete
20.3C disposable protected mobile E2E                        ➡️ operational closure
      protected login / UI / CSS / JS                        ✅
      disposable WRITE                                       ✅
      disposable READ                                        ✅
      fail-closed clarification                              ✅
      inspect disposable Markdown/Git evidence               ✅
      reconcile deployed n8n workflow drift                  ✅
      final protected browser clarification                  ✅
      stop disposable runtime / close test state             ⬜
20.3D real-vault activation                                  ⬜ human approval required
```

20.3B uses the dedicated `odyssey.ragdehl.com` Access application with the approved user identity, tunnel-side Access JWT validation, and a separate deny-by-default Access application covering only the five Odyssey paths on `n8n.ragdehl.com`; unrelated n8n root/admin behavior remains unchanged. The Cloudflare/certificate/Docker-DNS recovery details belong to the Phase 20.3 deployment document rather than this roadmap.

20.3C uses an isolated disposable vault/runtime/pending root before any real-vault product test. The protected mobile E2E now has successful WRITE, READ, and explicit clarification evidence, plus request-correlated Markdown/Git evidence. During clarification testing, a deployment-drift bug was found: the active n8n Odyssey product workflow had fallen behind the checked-in `workflows/odyssey-online.ts` contract. The existing active workflow was reconciled and republished without creating a second active endpoint, and the final protected browser clarification passed. Remaining work is operational shutdown/cleanup of the disposable runtime; real-vault reconnection is still outside 20.3C.

The first mobile E2E also exposed a product requirement: the visible chat currently does not carry conversation context into the planner, so a follow-up such as `¿Dónde vive?` safely abstains even after discussing one person. That future requirement is now owned by [Future Odyssey help and conversation context](future-help-and-conversation-context.md).

20.3D remains a separate human-controlled gate. Do not reconnect the public product flow to real personal knowledge merely because disposable E2E succeeds.

## Intended near-term order after Phase 20.3

Keep the order small and evidence-driven:

```text
finish 20.3 disposable shutdown + final verification
        |
        v
human-approved 20.3D real-vault activation
        |
        v
production / development isolation
        |
        v
conversation continuity foundation
        |
        v
real-usage-driven UI / capability work
```

The production/development split should happen before substantial new feature development so future disposable tests cannot affect real personal knowledge.

## Committed post-MVP directions

These are real product directions; exact implementation should remain incremental.

### Production and development isolation

Once real use depends on Odyssey, maintain a stable production deployment and a separate development/staging deployment so feature work and disposable tests cannot affect users or personal knowledge. `main` remains the production-ready source by default; feature branches feed development/staging before promotion. A permanent `develop` branch is optional and should be introduced only if repeated parallel integration work justifies it. See [Development Pipeline](development-pipeline.md#production-and-development-isolation).

### Natural conversation and history

Conversation continuity is now a concrete post-MVP requirement, not only a speculative idea. The intended architecture is **context on demand**, not a hard-coded “always send the last N messages” window.

```text
current request
      |
      v
same Luna-first planner
      |
      +--> self-contained -> execute normally
      |
      `--> context needed
               |
               v
       retrieve relevant conversation evidence
               |
               v
       same planner, bounded second pass
```

Conversation/history must remain a source/authority distinction, not an ordinary canonical note type. Visible conversation records should be durable Markdown-like non-knowledge state; historical retrieval must remain logically isolated from current personal-knowledge retrieval. Later coarse-to-fine navigation may use derived conversation/daily/weekly/monthly/yearly summaries that point back to raw conversations. See [Future Odyssey help and conversation context](future-help-and-conversation-context.md).

### Composable applications and capabilities

Applications should reuse shared Odyssey knowledge and lower-level capabilities rather than creating isolated stores or duplicate semantics. A useful target is composition such as:

```text
Reminders <- Tasks <- Projects
```

Planner/model extensibility must stay configuration-driven where semantics are already supported. The current planner derives note-type/property capabilities from `config/note-schema.json`; downstream model boundaries are generic with respect to concrete note types. The remaining application gap is executable manifest/registry routing for `DelegateAction`, not hard-coded app selection in the base planner. See [Architecture Overview](overview.md#configuration-driven-model-boundaries), [Future Extension Points](future-extension-points.md), and [Odyssey Platform Direction](odyssey-platform-direction.md).

### Multi-user shared knowledge

Support private and selectively shared knowledge only after authentication, authorization-before-retrieval, synchronization, conflict, and storage boundaries are explicit. A shared household list is an early concrete validation scenario.

See [Multi-user Collaboration Direction](multi-user-collaboration-direction.md).

## Later / conditional directions

The detailed index is [Future Extension Points](future-extension-points.md). Important preserved directions include:

- 💡 **Retrieval refinement from real misses:** first test query-decomposed multi-fact/entity-coverage retrieval; only then add candidate reduction or compact evidence if measured cost/volume justifies it. See [Future retrieval refinements](future-query-decomposed-retrieval.md).
- 💡 **Pending-reference evolution / schema coaching:** safely relink exact attributable occurrences and use repeated unresolved patterns only as advisory evidence for future schema proposals. See [Future pending-reference evolution](future-pending-reference-evolution.md).
- 💡 **Hierarchical conversation summaries:** conversation/day/week/month/year derived summaries may later narrow historical search before drilling down to raw supporting turns; they remain rebuildable navigation aids, never authority. See [Future Odyssey help and conversation context](future-help-and-conversation-context.md).
- 💡 **Usage/cost observability:** project already-collected safe operational/provider evidence into simple and advanced product views without creating a second tracing authority. This now explicitly includes integration/deployment provenance and a `MATCH | DRIFT | UNKNOWN` view of checked-in workflow source versus the active deployed workflow. See [Future product usage observability](future-product-usage-observability.md).
- 💡 **Capture-context provenance:** optional location/context belongs to fact/request provenance, not entity properties. See [Future capture-context provenance](future-capture-context-provenance.md).
- 💡 **Platform/local-first portability:** keep Core/data contracts usable by self-hosted, future local/mobile, app, and agent clients without making a central Odyssey server semantically mandatory. See [Odyssey Platform Direction](odyssey-platform-direction.md).
- 💡 **Direct Markdown/Obsidian edit ingestion:** eventually recognize authorized external edits, avoid self-trigger loops, validate only required normalization, refresh derived state, and audit accepted changes.
- 💡 **Structured analytics:** deterministic counts/sums/grouping over rebuildable structured/index data; do not load the whole vault into an LLM for arithmetic.
- 🔄 **Cost-aware model routing:** Luna-first production planning and Luna/medium contextual reasoning are active; retain bounded Sol fallback only where the validated production contract requires it and continue optimizing from measured telemetry rather than assumption.
- 💡 **Proactive resurfacing:** non-disruptive reminders/context suggestions only after direct usage demonstrates value.
- 💡 **Performance/index optimization:** optimize from measurements, not anticipated scale.

## Roadmap rule

This file records **current status and intended sequencing**, not every implementation detail. When a phase completes, update the status here and leave its detailed contract/evidence in the phase document, ADRs, tests, and benchmark records. Do not duplicate those historical narratives back into the roadmap.
