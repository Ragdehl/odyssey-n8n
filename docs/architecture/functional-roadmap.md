# Functional Roadmap

This is Odyssey's canonical source for **functional implementation status, intended order, and the next adoption gate**. Detailed contracts and historical evidence live in linked phase documents, ADRs, and benchmarks rather than being copied here.

Status: ✅ **IMPLEMENTED** · ➡️ **NEXT** · ⬜ **PLANNED** · 💡 **LATER / CONDITIONAL**

## Completed foundation

| Phase | Result |
| --- | --- |
| 9 | Deterministic exact entity resolution by canonical name/alias. |
| 10 | Local semantic entity candidate retrieval; similarity is evidence only. |
| 11 | Contextual/hybrid existing-entity resolution with deterministic Core validation. |
| 12 | Explicit deterministic entity persistence primitives. |
| 13 | General knowledge context retrieval (`get_context`) over rebuildable local indexes. |
| 14 | Validated top-level `RequestPlan` interpretation. |
| 15–15.3 | Semantic write planning, schema-aware selection/mutations, explicit links/tags, generic delegation preservation. |
| 16–16.7C | Safe create/update targeting, bounded UPDATE writing, deterministic CREATE, reference binding, bulk UPDATE, soft DELETE, and type migration. |
| 17A–17C | Executable Core application flow, durable pending work, and request-correlated local Git history. |
| 17D | Append-first atomic facts with request-derived fact locators and targeted correction/removal. |
| 17E | Pre-E2E schema/retrieval validation; unevidenced Combined Top-500 adoption withdrawn after identity-aware correction. |
| 18 | First real n8n -> runtime -> Core WRITE/READ end-to-end path. |
| 19 | Retry/failure hardening plus bounded timing/provider-usage evidence. |

Canonical/historical detail remains in the phase documents under this directory and in [Architecture Decisions](../decisions/README.md). The [Architecture Overview](overview.md) describes the current composed system without replaying this history.

## Current phase — UI-0 durable chat history/resume

Goal: make Odyssey conversations durable and resumable so closing/reopening the product does not lose visible history, while keeping conversation records isolated from canonical personal knowledge and preparing the later context-on-demand continuity flow.

Phase 23 is closed. UI-1 merged in PR #113 and is now fully deployed and human-verified on the authenticated production path. The final production checkpoint showed the request-detail `ⓘ` affordance, bounded execution details, estimated whole-request cost, and dated pricing basis. The promotion also exposed an active n8n workflow-projection drift failure; the bounded correction and reusable deployment rule are retained in [UI-1 production promotion evidence](ui-1-production-promotion.md).

Phase 22/23 identity adoption remains governed by the explicit production contract: trusted
production identity projection, real-user/person binding, and an explicit commit-selected
deployment with health/provenance verification. The selected commit is materialized in the
isolated production release worktree; merging `main` alone never changes PROD. The production
release-worktree and operator contract merged from PR #112 is preserved.
See [Phase 22 — self-identity contract](phase-22-self-identity.md) and [Future user self-identity binding](future-user-self-identity.md). The completed deployment/isolation foundation is documented in [Phase 21 — production/development isolation](phase-21-development-isolation.md) and the historical [Phase 20 — Odyssey Online MVP](phase-20-odyssey-online-mvp.md).

```text
20.0  consumer contract + architecture challenge             ✅ complete
20.1A offline grounded-answerer benchmark preparation        ✅ complete
20.1B focused live answerer model evidence                    ✅ complete
20.2A mobile web source + offline deterministic checks        ✅ complete
20.2B real n8n serving + Chrome Android validation            ✅ complete
20.2C planner incident hardening + focused live gate          ✅ complete
20.2D Luna-first planner experiment preparation               ✅ complete
20.2E Luna prompt-parity + atomicity validation               ✅ complete
20.2F Luna-first production planning + bounded Sol fallback   ✅ complete
20.2G contextual reasoner Luna replacement                    ✅ complete
20.3  protected Raspberry/Cloudflare deployment + E2E        ✅ complete
21A   isolation architecture challenge                       ✅ complete
21B   isolated DEV checkout/data + transient runtime proof   ✅ complete
21C   persistent DEV runtime/operations + DEV n8n decision   ✅ complete
21D   synchronized DEV n8n/routing pilot                     ✅ complete
Phase 21 production/development isolation                    ✅ complete
22A  self-identity architecture contract                    ✅ complete
22B  typed actor boundary + principal mapping foundation     ✅ complete
22C  explicit self-person binding                             ✅ complete
22D  authenticated human provenance propagation                ✅ complete
22E  deterministic self resolution                              ✅ complete
22F  focused isolated-DEV adoption gate                         ✅ complete
23A  production repository + live boundary inventory             ✅ complete
23B  trusted principal projection                                ✅ complete
23C  explicit production self binding                             ✅ complete
23D  reboot-safe production operator + provenance                ✅ complete
23E  read-only human-authenticated production SELF E2E            ✅ complete
UI-1 request detail / advanced inspector                         ✅ complete in PROD
UI-0 durable chat history/resume                                 ➡️ next
UI-2 read-only Notes                                              ⬜ planned
Tasks — first real application + minimal app routing              ⬜ planned
Projects — compose over Tasks                                     ⬜ planned
Reminders — lower-level time/reminder capability                  ⬜ planned
```

Latency optimization remains intentionally deferred: provider/model time dominates measured latency,
and no SELF/general or request-class fast path is authorized.

### 20.1B — answerer adoption gate

Complete. Frozen live evidence selected the inexpensive grounded answerer without weakening the bounded evidence contract. See [Phase 20.1 grounded-answerer benchmark](phase-20-1-grounded-answerer-benchmark.md).

### 20.2B — real browser integration

Complete. The checked-in `odyssey_web/` surface is served through the private n8n-facing product boundary. Raspberry-backed integration evidence covers the narrow request/response routes, and the physical Chrome/Android checkpoint covers the mobile UI, bounded delivery failure, restored controls, and explicit same-`request_id` Retry behavior.

### 20.2C — planner incident hardening

Complete. The production planner has explicit clarification, a bounded output envelope, zero automatic retries, and bounded post-parse validation diagnostics. See [Planner incident hardening](planner-incident-hardening.md).

### 20.2D–20.2F — Luna-first planner adoption

Complete. Luna/low inherited the strongest established RequestPlan semantics, passed the focused prompt-parity/atomicity gates, and is now the production first pass. Safe PLAN/CLARIFY returns directly; structured fail-closed may invoke one bounded Sol/low fallback. Separate provider-call evidence preserves the real Luna/Sol usage split. See [Phase 20.2F — Luna-first production planning](phase-20-2f-luna-first-production.md).

### 20.2G — contextual reasoner Luna replacement

Complete. The full frozen 90-case Luna/medium benchmark produced 88/90 frozen-label accuracy, 35/35 correct `RESOLVED` decisions, zero clear false `RESOLVED`, and zero invalid outputs. Production now uses Luna/medium with the same canonical ten-example calibration prefix. See [Phase 20.2G — contextual reasoner Luna replacement gate](phase-20-2g-contextual-luna-gate.md).

### 20.3 — protected deployment

Complete and merged in PR #103. The protected Cloudflare boundary, disposable mobile E2E, production-vault Git bootstrap/index rebuild, and bounded real-runtime activation were all verified before merge.

```text
20.3A deployment/security inventory                          ✅ complete
20.3B protected hostname + Access + tunnel JWT enforcement   ✅ complete
      exact Odyssey-path bypass closure on n8n hostname      ✅ complete
20.3C disposable protected mobile E2E                        ✅ complete
      protected login / UI / CSS / JS                        ✅
      disposable WRITE                                       ✅
      disposable READ                                        ✅
      fail-closed clarification                              ✅
      inspect disposable Markdown/Git evidence               ✅
      reconcile deployed n8n workflow drift                  ✅
      final protected browser clarification                  ✅
      stop disposable runtime / close test state             ✅
20.3D real-vault activation                                  ✅ complete
      exact /data/odyssey/vault Git root + baseline          ✅
      rebuildable production indexes reset/rebuilt           ✅
      private production runtime health/listening verified   ✅
```

20.3B uses the dedicated `odyssey.ragdehl.com` Access application with the approved user identity, tunnel-side Access JWT validation, and a separate deny-by-default Access application covering only the five Odyssey paths on `n8n.ragdehl.com`; unrelated n8n root/admin behavior remains unchanged. The Cloudflare/certificate/Docker-DNS recovery details belong to the Phase 20.3 deployment document rather than this roadmap.

20.3C used an isolated disposable vault/runtime/pending root before any real-vault product test. The protected mobile E2E has successful WRITE, READ, and explicit clarification evidence, plus request-correlated Markdown/Git evidence. During clarification testing, a deployment-drift bug was found: the active n8n Odyssey product workflow had fallen behind the checked-in `workflows/odyssey-online.ts` contract. The existing active workflow was reconciled and republished without creating a second active endpoint, and the final protected browser clarification passed. At the 20.3C close the disposable runtime and test state were stopped/removed and port `8765` was free; 20.3D subsequently activated the separate real production runtime after the authorized vault bootstrap.

20.3D initialized `/data/odyssey/vault` as the exact production Git repository root with empty baseline commit `465773757427597b1f6036e94e670c8dd360d882`, reset only the guarded rebuildable `context.sqlite3` and `semantic.sqlite3` indexes, rebuilt them from the empty canonical vault, and started the private production runtime. Post-start evidence showed HTTP 200 on `172.18.0.1:8765/healthz`, with no listener on `127.0.0.1:8765`. No synthetic personal WRITE was used for activation.

The first mobile E2E also exposed a product requirement: the visible chat currently does not carry conversation context into the planner, so a follow-up such as `¿Dónde vive?` safely abstains even after discussing one person. That future requirement is now owned by [Future Odyssey help and conversation context](future-help-and-conversation-context.md).

## Phase 21 status — production and development isolation

Phase 21A–21D are complete. Odyssey now has a persistent isolated DEV source/data/runtime boundary, an on-demand separate DEV n8n stack, a fixed Access-protected DEV browser endpoint, deployment provenance/drift checks, and verified production non-interference.

The first real personal production cycle is complete. On 2026-09-11 the mobile UI wrote `Me llamo Edgar, soy data engineer y trabajo en Alten para Airbus`, producing one canonical `person` note for Edgar with two atomic facts and a request-correlated Git commit/index refresh; the subsequent mobile READ `¿Dónde trabaja Edgar?` returned `Edgar trabaja en Alten para Airbus.` No synthetic benchmark request was used for this milestone.

```text
first real personal use                               ✅ complete
        |
        v
production / development isolation                    ✅ complete
        |
        v
user self-identity binding to ordinary person note    ✅ complete
        |
        v
UI-1 request feedback / advanced inspector            ✅ complete in PROD
        |
        v
UI-0 durable chats + resume / conversation continuity ➡️ next
        |
        v
UI-2 read-only Notes
        |
        v
Tasks -> Projects -> Reminders application validation
        |
        v
Activity / editing / analytics ordered by real use
```

The production/development split now precedes substantial new feature development so future disposable tests cannot affect real personal knowledge. See the [Phase 21 evidence](phase-21-development-isolation.md).

The self-identity implementation is complete and Phase 23 production adoption is closed. The person note stays in the normal vault/search/statistics surface; only the account/actor binding is separate identity state. The tracked reboot-safe `odyssey-prod` operator is human-gated, and cloudflared lifecycle remains outside it. See [Phase 22 contract](phase-22-self-identity.md), [Phase 23 production adoption](phase-23-production-self-identity-adoption.md), and [Future user self-identity binding](future-user-self-identity.md).

## Committed post-MVP directions

These are real product directions; exact implementation should remain incremental.

### Production and development isolation

Once real use depends on Odyssey, maintain a stable production deployment and a separate development/staging deployment so feature work and disposable tests cannot affect users or personal knowledge. `main` remains the production-ready source by default; feature branches feed development/staging before promotion. A permanent `develop` branch is optional and should be introduced only if repeated parallel integration work justifies it. See [Development Pipeline](development-pipeline.md#production-and-development-isolation).

```text
21A architecture/isolation decision                         ✅ complete
21B transient isolated runtime proof                        ✅ complete
21C persistent isolated DEV runtime/operator workflow       ✅ complete
21D on-demand DEV n8n + fixed protected browser endpoint    ✅ complete
Phase 21 production/development isolation                   ✅ complete
```

The DEV environment has fixed source/data/runtime identities and an on-demand separate n8n
database/container. It is not a permanent Git branch. The fixed protected endpoint and human
browser checkpoint are complete; ordinary feature work should continue through isolated DEV before
explicit human-gated production promotion.

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

The approved user interaction model is **automatic routing by default, explicit routing when useful**. Ordinary users should speak naturally in any Odyssey chat; the relevant capability is selected internally and only that selected capability should execute/respond. Optional syntax such as `@Tasks` may direct or disambiguate a request but must never be required. App-specific chats may exist as secondary focused entry points while reusing the same knowledge, identity and history rather than creating silos. Applications may show a small capability identity in the UI, but should not become independent personalities that all listen to every message. Full nested threads are deferred; a simpler “continue in new chat from this message” pattern should be tried first if branching becomes useful.

The first real application is **Tasks**, chosen to prove the smallest practical manifest/routing/state contract. **Projects** follows by reusing Tasks, and **Reminders** supplies the lower-level time/reminder capability where justified. Do not build a generic plugin platform before Tasks proves what the common application contract actually needs.

Planner/model extensibility must stay configuration-driven where semantics are already supported. The current planner derives note-type/property capabilities from `config/note-schema.json`; downstream model boundaries are generic with respect to concrete note types. The remaining application gap is executable manifest/registry routing for `DelegateAction`, not hard-coded app selection in the base planner. See [Architecture Overview](overview.md#configuration-driven-model-boundaries), [Future Odyssey product interface](future-product-interface.md#application-interaction--automatic-by-default-explicit-when-useful), [Future Extension Points](future-extension-points.md), and [Odyssey Platform Direction](odyssey-platform-direction.md).

Once application work becomes repetitive, evaluate a bounded **agent-assisted delivery loop**: human + assistant approve a feature contract and validation criteria, an implementation agent works only in isolated DEV, deterministic checks run first, an independent validation agent reviews from fresh context, and only a final evidence-backed PR returns to the human for acceptance. This automation should not be introduced during Core architecture work and must never autonomously merge/promote production. Detailed guardrails and scheduling direction live in [Future Extension Points](future-extension-points.md#agent-assisted-application-delivery).

### Multi-user shared knowledge

Support private and selectively shared knowledge only after authentication, authorization-before-retrieval, synchronization, conflict, and storage boundaries are explicit. A shared household list is an early concrete validation scenario. Each authenticated actor should be able to bind to its own ordinary canonical `person` note without creating a special `user` knowledge type or per-application profile copy.

See [Multi-user Collaboration Direction](multi-user-collaboration-direction.md) and [Future user self-identity binding](future-user-self-identity.md).

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
- 💡 **Agent-assisted app delivery:** after application work becomes routine, queue only human-approved feature contracts and let bounded implementation/validation agents work in isolated DEV with deterministic gates, explicit budgets, no autonomous merge/promotion, and final human acceptance. See [Future Extension Points](future-extension-points.md#agent-assisted-application-delivery).
- 🔄 **Cost-aware model routing:** Luna-first production planning and Luna/medium contextual reasoning are active; retain bounded Sol fallback only where the validated production contract requires it and continue optimizing from measured telemetry rather than assumption.
- 💡 **Proactive resurfacing:** non-disruptive reminders/context suggestions only after direct usage demonstrates value.
- 💡 **Performance/index optimization:** optimize from measurements, not anticipated scale.

## Roadmap rule

This file records **current status and intended sequencing**, not every implementation detail. When a phase completes, update the status here and leave its detailed contract/evidence in the phase document, ADR, tests, and benchmark records. Do not duplicate those historical narratives back into the roadmap.