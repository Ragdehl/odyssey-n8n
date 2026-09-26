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

## Current functional phase — semantic set resolution and evidence design

[Performance / Latency / Cost P1](performance-cost-p1.md) is complete. Its baseline found that the
universal Luna → Sol route was a local Luna planner-result validation mismatch after successful
provider completion, not a provider failure. The envelope repair restored direct valid Luna planning.
The one measured avoidable contributor was duplicated Structured Outputs schema material: PR #129
reused local `$defs` / `$ref` definitions without changing the planner language or semantic validators.
The Luna schema fell from 35,662 to 9,694 serialized bytes (72.8%), planner input from roughly 11.87k
to 7.15k tokens, and the representative Luna-only READ / WRITE / CLARIFY gates took 2.963 s / 2.143 s
/ 1.934 s with no Sol fallback. Small later prompt/capability probes did not establish a reliable
input-size/latency relationship; provider/model base latency and variance now dominate the remaining
roughly 2–3 seconds. P1 therefore stops here: no request-type-specific schema or fast path is planned.
PR #129 merged at `1c2f0c45672e8d1d917cf6abd271a85123100b8e` and was explicitly deployed to isolated
DEV, where runtime and DEV n8n health and provenance were `MATCH`; PROD was untouched.

The provider-free [Reference & Relationship Resolution v1 Slices 1–2](post-ui2-note-creation-and-schema-evolution.md#proposed-implementation-slices)
are implemented. Slice 3 now has a Draft implementation of the relational planner contract and
minimal Core read/write bridge on a feature branch; its frozen ten-case production model gate is
**pending review** after three bounded attempts. Attempt 1 at
`2405b136fc9abe686efb49599ba6368e479fe71a` stopped before provider construction because its shell
had not exported the protected `OPENAI_API_KEY`; its retained evidence has zero rows. Attempt 2 at
`e17b5f750573e39aebf8477e933902e083ad7f9f` used the verified same-shell export procedure and
reached three Luna-only cases within the $0.455998 ceiling: R01/W01 passed, then W02 safely clarified
instead of producing the required complete-set shared-fact write (`FAIL_CLOSED`). It stopped with no
Sol fallback; actual recorded cost was $0.00250944. The follow-up added one non-evaluation Luna
complete-set source-write teaching example without changing the frozen W02 case/oracle or
deterministic Core. Attempt 3 at `0c28855f35b39f4429ae2fc60db180a38fe3b9d6` then passed R01,
W01, W02, C01, P01, S01, and S02 Luna-only; W02 used the required complete-set source-write shape.
S03 required one Sol fallback after Luna's local `KNOWLEDGE_UNIT` / `INVALID_FIELDS` validation
failure. The runner retained the passing fallback row and stopped as required: 8 attempted cases,
8 Luna calls, 1 Sol call, $0.05772924 actual cost, and the expected W02 `source_selector_review`
flag. Review accepts that W02 selector as natural-language source intent (`ayer`) and accepts S03
as a passing production fallback: its final Sol plan preserves ordinary Marta/Airbus
`KnowledgeReference` semantics. S04/S05 were not attempted. A fixed, unexecuted continuation for
only S04/S05 has a $0.36979880 ceiling for at most three calls and requires separate explicit human
authorization. That $0.37 authorization was recorded at
`828672cc4597c1931853cf32d1fa90330eccf25b`; the continuation ran once at the same HEAD and passed
S04/S05 Luna-only. S04 preserved ordinary `all_matching` tag-add semantics and S05 preserved two
independent ordinary Marta facts. It made 2 Luna calls, no Sol calls or fallbacks, and cost
$0.00216274. All ten frozen cases have reviewed evidence, so the focused Slice 3 model gate
passed within the bounded v1 contract. Slice 3 and v1 merged in PR #133. A subsequent DEV smoke
exposed the generic read-path gap: one canonical shared fact was visible in UI-2 backlinks but was
absent from ordinary entity-answer context. The merged Core request-aware, one-hop source-fact
enrichment keeps direct entity notes primary; current canonical incoming/outgoing snippets are
locally ranked and serialized with actual source provenance, without graph traversal or copied
member prose. The existing
current-Markdown, one-source, one-hop evidence boundary, shared-fact home, inverse/symmetric
evidence policy, and all-or-clarify rule remain the v1 contract. UI-1 request detail is complete in PROD;
its production promotion evidence is in [UI-1 production promotion](ui-1-production-promotion.md).

[Semantic set resolution and evidence](semantic-set-resolution-and-evidence.md) is underway in Draft
PR #142. The approved simplification keeps three distinct retrieval shapes: ordinary single-topic
answers, matching Notes as objects via existing `presentation_intent=note_set`, and canonical-fact
collections via `RetrieveAction.result_shape=collection`. The planner preserves the lossless query
without a generated subject/member ontology; Core owns bounded evidence, linked/literal grounding,
and the decision between answer, genuine clarification, and cannot-answer. Multiple valid results
are not ambiguity. Previous planner-only gates remain historical evidence for their older frozen
contracts; the changed model-facing contract still needs focused live regression evidence before
readiness. No generic Note or type is added. Answer-source Note navigation (#138), progress
(#136), and direct Notes CRUD (#134) remain separate acceptance boundaries until implemented and
verified. PR #142 now includes a deliberately narrow clarification-continuation (#137) slice:
one durable bounded choice for a singular Note read or one write target, with cancel/new-request
handling and current-Markdown re-grounding before resume. Broader staged/multi-action continuation
remains deferred. The v7 combined Luna/low gate ran once across 22 frozen planner/classifier cases
and completed 19 PASS / 3 safe FAIL: SSET02/SSET03 exposed the generic collection-adoption gap and
HD03 exposed a stale historical oracle. The deterministic correction was green. The final
18-case planner-only Luna/low recheck was attempted once on 2026-09-26 at
`48686b0eff3375d11f8c51a94e0b37b57adb0139`, using
`benchmarks/.live-results/semantic-set-slice1-v7-final-planner-recheck-luna-gate.jsonl`. It stopped
at SSET01 with `FAIL_CLOSED` before a validated planner result because the provider connection
failed during DNS resolution (`APIConnectionError -> ConnectError -> ConnectError -> gaierror`).
One provider request was attempted; there was no response or token usage, no retry, and the
remaining 17 planner cases were not reached. CLAR01–04 were not rerun because the
clarification-classifier contract/code is unchanged. The planner live gate remains incomplete and
requires review before any further live authorization; no production or DEV readiness is claimed.
The single authorized retry on `89d9c3c82c5bf32d1c2e7f6b49046052a5ac7d5d` also stopped at SSET01
before a validated response with the same DNS-resolution chain. Its separate immutable artifact
`benchmarks/.live-results/semantic-set-slice1-v7-final-planner-recheck-luna-gate-retry1.jsonl`
contains one `FAIL_CLOSED` row; one request was attempted, usage was unavailable, no retry occurred,
and the other 17 cases were not reached. No further retry is authorized by that attempt. Tasks and
Events remain later directions.

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
UI-0 durable main conversation/continuity                        ✅ complete in PROD
UI-0 explicit production promotion                              ✅ complete
UI-2 read-only Notes                                              ✅ merged in PR #124
Performance / Latency / Cost P1                                  ✅ complete
Reference & Relationship Resolution v1 Slice 1                    ✅ complete
Reference & Relationship Resolution v1 Slice 2                    ✅ complete
Reference & Relationship Resolution v1 Slice 3                    ✅ merged in PR #133
Semantic set resolution and evidence architecture challenge        ➡️ design Draft PR
Tasks — first real application + minimal app routing              ⬜ planned
Events / Calendar — high-value time-aware capability              ⬜ prioritized after Tasks
Reminders — lower-level delivery for Tasks / Events               ⬜ planned as needed
Maintainability checkpoint — bounded cleanup after calendar path  ⬜ planned
Projects — compose over Tasks                                     ⬜ planned after checkpoint
```

Earlier latency observations motivate P1 but do not predetermine its bottleneck or authorize a fast path.

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

20.3B originally established the dedicated `odyssey.ragdehl.com` Access application with the approved user identity, tunnel-side Access JWT validation, and a separate deny-by-default Access application covering the then-current five Odyssey paths on `n8n.ragdehl.com`; unrelated n8n root/admin behavior remained unchanged. UI-0 later expanded that alternate-host Access set to seven by adding `/api/environment.js` and `/api/conversation`, with unauthenticated redirect evidence for both. The Cloudflare/certificate/Docker-DNS recovery details belong to the Phase 20.3 deployment document rather than this roadmap.

20.3C used an isolated disposable vault/runtime/pending root before any real-vault product test. The protected mobile E2E has successful WRITE, READ, and explicit clarification evidence, plus request-correlated Markdown/Git evidence. During clarification testing, a deployment-drift bug was found: the active n8n Odyssey product workflow had fallen behind the checked-in `workflows/odyssey-online.ts` contract. The existing active workflow was reconciled and republished without creating a second active endpoint, and the final protected browser clarification passed. At the 20.3C close the disposable runtime and test state were stopped/removed and port `8765` was free; 20.3D subsequently activated the separate real production runtime after the authorized vault bootstrap.

20.3D initialized `/data/odyssey/vault` as the exact production Git repository root with empty baseline commit `465773757427597b1f6036e94e670c8dd360d882`, reset only the guarded rebuildable `context.sqlite3` and `semantic.sqlite3` indexes, rebuilt them from the empty canonical vault, and started the private production runtime. Post-start evidence showed HTTP 200 on `172.18.0.1:8765/healthz`, with no listener on `127.0.0.1:8765`. No synthetic personal WRITE was used for activation.

The first mobile E2E exposed the need for bounded immediate conversation continuity: a follow-up such
as `¿Dónde vive?` safely abstained after discussing one person. UI-0 later implemented that need with
one bounded recent-turn window while keeping canonical notes/facts authoritative. The durable
conversation/context contract is owned by [Future Odyssey help and conversation context](future-help-and-conversation-context.md) and [UI-0 durable main conversation](ui-0-durable-conversations.md).

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
UI-0 durable main conversation / continuity           ✅ complete in PROD
        |
        v
UI-2 read-only Notes                                   ✅ merged
        |
        v
Performance / Latency / Cost P1                       ✅ complete
        |
        v
Reference & Relationship Resolution v1 Slice 1        ✅ complete
Reference & Relationship Resolution v1 Slice 2        ✅ complete
Reference & Relationship Resolution v1 Slice 3        ✅ merged in PR #133
Semantic set resolution and evidence design           ➡️ architecture challenge
        |
        v
Tasks — first application contract
        |
        v
Events / Calendar — prioritized time-aware capability
        |
        v
Reminders as needed by Tasks / Events
        |
        v
bounded maintainability checkpoint
        |
        v
Projects / Activity / editing / analytics by real use
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

Conversation continuity is a concrete post-MVP requirement, delivered first as one persistent main
chat rather than chat management. A deterministic bounded recent-turn window accompanies the current
request in the existing Luna-first planner call. It may resolve conversational wording but never
becomes a current-fact source or retrieval expansion; the validated plan continues to route to
canonical Markdown only. Historical knowledge questions belong to canonical notes, fact-capture
chronology, and canonical Git/request history. Transcript search, summaries, topic splitting, and
multiple-chat UX are not UI-0 follow-on roadmap work; any such product would require separate
justification. See [Future Odyssey help and conversation context](future-help-and-conversation-context.md).

### Composable applications and capabilities

Applications should reuse shared Odyssey knowledge and lower-level capabilities rather than creating isolated stores or duplicate semantics. A useful target is composition such as:

```text
Projects -> Tasks
             |
             v
         Reminders

Events ------+
```

The approved user interaction model is **automatic routing by default, explicit routing when useful**. Ordinary users should speak naturally in the main conversation; the relevant capability is selected internally and only that selected capability should execute/respond. Optional syntax such as `@Tasks` may direct or disambiguate a request but must never be required. A capability-specific surface may exist only when a concrete need justifies it, while reusing the same knowledge, identity, and application state rather than becoming a silo. Applications may show a small capability identity in the UI, but should not become independent personalities that all listen to every message. Nested threads and branching chat management are not committed directions.

The first real application is **Tasks**, chosen to prove the smallest practical manifest/routing/state
contract. Once that contract is proven, **Events / Calendar** is the next prioritized application
area because time-aware personal behavior is unusually useful in everyday Odyssey use. **Reminders**
should provide only the lower-level notification/delivery semantics that Tasks and Events actually
need; it must not collapse tasks and events into one model. **Projects** remains a committed consumer
of Tasks but can follow the calendar path and the bounded maintainability checkpoint rather than
blocking Events. See [Future Events / Calendar capability](future-events-calendar.md).

Do not build a generic plugin platform before Tasks proves what the common application contract actually needs.

Planner/model extensibility must stay configuration-driven where semantics are already supported. The current planner derives note-type/property capabilities from `config/note-schema.json`; downstream model boundaries are generic with respect to concrete note types. The remaining application gap is executable manifest/registry routing for `DelegateAction`, not hard-coded app selection in the base planner. See [Architecture Overview](overview.md#configuration-driven-model-boundaries), [Future Odyssey product interface](future-product-interface.md#application-interaction--automatic-by-default-explicit-when-useful), [Future Extension Points](future-extension-points.md), [Future Events / Calendar capability](future-events-calendar.md), and [Odyssey Platform Direction](odyssey-platform-direction.md).

Once application work becomes repetitive, evaluate a bounded **agent-assisted delivery loop**: human + assistant approve a feature contract and validation criteria, an implementation agent works only in isolated DEV, deterministic checks run first, an independent validation agent reviews from fresh context, and only a final evidence-backed PR returns to the human for acceptance. This automation should not be introduced during Core architecture work and must never autonomously merge/promote production. Detailed guardrails and scheduling direction live in [Future Extension Points](future-extension-points.md#agent-assisted-application-delivery).

### Maintainability checkpoint after the calendar/application foundation

Maintainability is a continuous acceptance concern during every phase, but Odyssey should not pause
useful product work now for speculative restructuring. The near-term priority is P1, then bounded
post-UI-2 knowledge work, then Tasks and Events / Calendar with the minimum Reminder semantics
those capabilities need.

After that path has exercised the application boundary in real code, schedule a **bounded
maintainability checkpoint** before substantial secondary-app expansion. The checkpoint should use
actual change pain and duplication as evidence: retire proven legacy, consolidate genuinely repeated
contracts, split modules that have accumulated unrelated responsibilities, and strengthen fragile
contract tests. It is explicitly **not** a rewrite, architecture reset, or demand to DRY across
intentional trust-boundary validation.

Current watchpoints and the per-phase reuse/refactor discipline are owned by the
[Development Pipeline](development-pipeline.md#maintainability-guard-during-feature-work).

### Multi-user shared knowledge

Support private and selectively shared knowledge only after authentication, authorization-before-retrieval, synchronization, conflict, and storage boundaries are explicit. A shared household list is an early concrete validation scenario. Each authenticated actor should be able to bind to its own ordinary canonical `person` note without creating a special `user` knowledge type or per-application profile copy.

See [Multi-user Collaboration Direction](multi-user-collaboration-direction.md) and [Future user self-identity binding](future-user-self-identity.md).

## Later / conditional directions

The detailed index is [Future Extension Points](future-extension-points.md). Important preserved directions include:

- 💡 **Retrieval refinement from real misses:** first test query-decomposed multi-fact/entity-coverage retrieval; only then add candidate reduction or compact evidence if measured cost/volume justifies it. See [Future retrieval refinements](future-query-decomposed-retrieval.md).
- 💡 **Pending-reference evolution / schema coaching:** safely relink exact attributable occurrences and use repeated unresolved patterns only as advisory evidence for future schema proposals. See [Future pending-reference evolution](future-pending-reference-evolution.md).
- 💡 **Historical canonical-knowledge retrieval:** extend note/fact chronology and canonical Git/request-history access only when a concrete historical knowledge question requires it; do not substitute chat-history search. See [Future Odyssey help and conversation context](future-help-and-conversation-context.md).
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
