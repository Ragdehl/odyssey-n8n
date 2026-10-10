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

## Deferred model consolidation — user decision (2026-10-10)

**Do not change models during the current Router fact-candidate / Temporal / Core work.**
The user explicitly prefers finishing and validating this functional block
first, keeping its existing configured models and historical live-gate evidence
stable. **After this block is closed**, schedule a separate reviewed effort to
migrate remaining Odyssey components to **GPT-6 Luna** (including Core Planner,
Core Attribution, Writer, Fact Selector, clarification and contextual reasoning,
where still on GPT-5.6 Luna). Inventory actual runtime overrides as well as
code defaults; preserve prompt/contract and cost benchmarks, run focused live
model-quality gates under separately agreed budgets, then request approval
for DEV/PROD promotion. This is **deferred work**, not an authorization to
silently switch models, merge or deploy now.

## Router parallel preparation (DEV optimization)

[Router parallel preparation, Slices 1–2](router-parallel-preparation.md) allows
independent validated Router spans (Core, Tasks, Temporal) to run their
app-specific interpretation when needed **and shared Core model planning**
concurrently (up to two workers). The existing Core
execution boundary alone handles identity resolution, preflight, pending work,
Git and canonical writes **sequentially in route order**. Production still defaults
to sequential, with the preparation enabled only in isolated DEV. Do not confuse
concurrent Core *model planning* with parallel Core *execution*, and do not claim
measured latency savings from deterministic concurrence tests alone.

## Planned Router fact-candidate segmentation — design review

[Router fact-candidate units v1](router-fact-units-v1.md) records the user-reviewed direction for independent atomic candidate assertions, typed source-context inheritance, and separation from Core-owned persistence. Its 22 user-agreed plus four additional generic-subject future oracles are not a live Router contract, and the current `dev` Router v0 remains unchanged. Frontend Block 3 preparation now makes existing validated v1 route evidence legible, provides an optional read-only renderer for the inactive bounded checkpoint shape, and supplies a local test-only candidate preview; none crosses a product transport or grants write/identity authority. The approved partial-write direction retains validated independent facts while ambiguity remains pending with targeted clarification, not blanket abort. Diagnostic checkpoints/graph come before any v1 provider/runtime activation; product choices about partial writes and conditional/negative persistence remain open.

**Router candidates Block 4A (feature branch, not activated):** the closed
source-anchored parser and injected one-call proposal adapter are implemented for
the 26 design cases / 56 candidates. Roles and inheritance remain unverified
linguistic evidence with no Note type, Core write, runtime dispatch or new
frontend transport. Read-only Router→Temporal source-scope and Core-owned
candidate evidence/prompt opt-in are also prepared on the feature branch,
including one fully injected provider-free F13 vertical planner test. No
runtime branch uses these new contracts and none executes candidate writes.
Disposable Markdown tests now exercise existing Core persistence for three
activities across two dates, one shared two-item purchase, exact-request replay
and an ambiguous pronoun held out of synthetic writes. A Core-owned read-only
receipt observer exposes genuine unit statuses but deliberately leaves **all**
source candidates `unattributed`, since ordinals alone cannot prove a semantic
candidate was persisted. The existing Core result may say `completed` despite
an unresolved candidate deliberately omitted by a handwritten test plan; this
shows why per-candidate Core-verified attribution, pending clarification and
partial-success/idempotence guards still need implementation before activation.
Additional bounded readback now checks Core's actual canonical Markdown
fact markers by request ID, fact ordinal, stable Note ID and exact plan text.
It distinguishes confirmed physical writes from cross-request duplicate
suppression, `unproven` source candidates, ambiguous candidates and unknown
source coverage, and explicitly
forbids reporting the whole request as complete on Core fact markers alone.
An **opt-in Core preflight** now rejects missing candidate coverage or
unreviewed complex writes before any mutation, without touching Router v0.
If synthetic independent writes succeed while a candidate remains unresolved,
opt-in Core marks the request `PARTIAL` and explicitly reports that the
candidate continuation is **not durably resumable yet**. Structural attribution
is not proof that the right semantic fact was written; the new conservative
Core preflight now rejects a deliberately swapped pan/milk mapping, but does
not certify semantics. A Core-owned model-approved
mapping/semantic proof, safe reference handling, durable partial clarifications,
new request-detail projections and a true provider→verified attribution→Core
write vertical path, plus separate final live GPT-6 Router / GPT-5.6 Luna
semantic gates, remain required. Router v0 remains operational. The
isolated Core candidate preflight additionally rejects obvious mismatched
item evidence, a newly invented negation, and unverified source pronoun
references **before persistence**. Passing these vetoes is not semantic
attestation: mixed-clause negation, date ownership and grounded canonical
identity still require independent verification.

The human-approved partial clarification lifecycle now has an isolated v2
nonknowledge state store under `state/pending/candidates/`, leaving v1 planned
pending records and all canonical Notes intact. The opt-in Core callback
records a real pending candidate **only after** verifying written Markdown,
including original request/ordinal/target/fact digests; selections remain
Core-grounded, request-ID scoped and replay/staleness guarded. Synthetic
`Eric y Luis → él` tests now cover `con Luis`, cancellation (including after
selection), unrelated/multiple clarifications, restart, option changes and
previous fact changes. A guarded Core continuation with a pre-reviewed plan
writes only the outstanding cinema Day link, with original capture clock and
all previously saved facts unchanged. These remain **provider-free fixtures**;
no live model has produced an accepted continuation, no auto-close-to-resolved
semantic contract is claimed, and the v2 route is not wired into runtime.
Final model semantic gates plus the historical release hash/operator blockers
remain before any DEV activation.
Initial authorized GPT-6 Router/GPT-5.6 Luna live smoke (2026-10-10):
4 frozen synthetic source cases, **6** real zero-retry read-only model calls,
**$0.004006 estimated** standard-rate input/output cost; F11/F01/F13 passed
Router candidate counts/states, but F14 grouped `hablé con Eric y Luis`
into one conversation (2 units total), while the frozen oracle requires
3 independently accounted source facts. Pronoun remained explicitly ambiguous.
F11 Core attribution passed local source/fact checks and a real Core Luna
planner returned a nonexecuted validated 1-action plan, without semantic
execution proof. This is an **evidence-backed readiness FAIL**, not a model-
quality acceptance gate or permission to silently alter the human fixture.
The coordinated-participants granularity requires product adjudication; full
held-out model/continuation gates and historical release failures remain.

**Approved 2026-10-10 candidate granularity:** One coherent event may have
multiple canonical participants without inventing simultaneity. F14 now has
one linked Eric+Luis event plus a pending ambiguous `él` (2 source candidates).
F27 preserves the earlier distinct-conversation/ambiguous-pronoun behavior
using explicit "después" (3 source candidates). The immutable v1 design matrix and its frozen benchmark test stay at
26 cases / 56 candidates. The separately versioned approved v2 oracle has
27 cases / 58 candidates. In the **isolated Core pilot only**, a review-gated
one-event/two-named-reference plan persists one actual Day fact and two valid
canonical backlinks; this is also tested for two project Notes. Current guarded
Core write readback checks real rendered wikilinks and saves their digest for
pending continuity. A synthetic pre-reviewed follow-up writes only the
outstanding cinema fact and reuses original captures; no duplicates. The
user-approved semantics resolved the F14 unit-count disagreement in the prior
live smoke, not its still-unverified `plan` vs oracle `occurrence` kind,
or any held-out model quality gate. The separate Core-only Luna-attribution
proposer now accepts **only the same bounded two-name, two-link Core plan**
for untrusted source/fact matching; its existing model JSON and instructions
are unchanged and it cannot authorize a write. Provider-fake negative tests
prove omitted/swapped/extra helpers still fail closed. No normal runtime or
DEV activation yet.

**Experimental F14 semantic-plan compilation, 2026-10-10 (feature branch):**
The Core semantic compiler and Temporal evidence validators now support a
**strictly source-scoped omitted future date** when and only when an opt-in
unverified candidate is explicitly ambiguous and uniquely owns that exact
Temporal text plus original date/time role. The ordinary full-source Temporal
input remains unchanged; only a non-authoritative, Core-owned validation copy
excludes the pending mention. Missing safe dates, incorrect target days,
ambiguous repeated date text and absent scoped role still fail closed.
A frozen provider-shaped semantic WRITE now passes the actual Luna semantic
decoder and Core plan compiler and, subject to an **independently reviewed**
Core coverage manifest, persists one safe Eric+Luis linked Day fact with
`2026-10-03` anchor while durable v2 pending state retains the cine clause for
`2026-10-05`. No plan generated by a real provider has passed this new shape
or its semantic acceptance gate; no DEV activation, provider expense or changes
to model-facing prompts, output schemas, canonical NoteSchema or Router v0.

**V2 live gate blocker and offline cost decomposition (2026-10-10):**
The attempted large remote operation to author a second live evaluator was
blocked by the ChatGPT platform before remote execution; neither API nor Pi
reported an error. The separate offline-only audit
`benchmarks/fact_candidate_v2_preflight/check.py` now computes the actual
provider-request envelopes from fake-client production constructors for
F14/F27/F09/F10, with no API, secrets, writes or deployment. The conservative
full 9-call envelope is ~USD 0.0848571, above the user-authorized USD 0.02;
a potential limited 6-call Router/Temporal wave totals ~USD 0.013495.
Only an explicitly security-permitted and reviewed live-gate workflow may
execute that wave; the file is not an alternate live runner or circumvention.
See issue #151 for the historical blocked inline operation, which was
not retried.

**Actual v2 Router-only GPT-6 live evidence (2026-10-10):** A separate
versioned/snapshot-checked runner was accepted through the ordinary Pi user
service without changing the model, prompt, schema or user vault. Four synthetic
Router calls F14/F27/F09/F10 completed (2,134 input and 1,575 output tokens;
pinned standard-rate cost estimate **$0.0010009**, conservative pre-call bound
**$0.01181875** vs previously approved $0.02). The strict frozen fixture
comparison failed for all four because of shape differences, **but the
semantic split itself failed clearly on F09** (two independent residences
wrongly grouped into one relationship). F10 returned a correct single mutual
relation with different grounded spans. F14/F27 correctly distinguished one
coherent vs two sequential contact events and left `él` ambiguous, but
misclassified the future as `plan`, supplied noncanonical date role labels
and lacked Core-required participant/reference evidence; offline replay of
the **real model replies** is rejected by Core's canonical source coverage
preflight before any write. Saved synthetic responses and regression tests
are versioned under `benchmarks/fact_candidate_v2_live/`. **The limited
real-model evaluation is now unblocked and completed; Router v1 is still
NOT READY for DEV**, pending contract/prompt semantic corrections and a
reviewed new regression gate. That success does not determine the cause of
the older rejected remote shell command or authorize bypassing it.

**Second focused GPT-6 Router gate, opt-in prompt v2 (2026-10-10):** The
entire previous source-only prompt was retained and supplemented with generic
independent-property, mutual-relation, date, pronoun and future-event rules
without changing the model/schema or runtime. Four synthetic live calls
completed with 3,634 input / 1,389 output tokens and an estimated standard
USD **0.0010579** charge. F09 now separates Marta and Luis into **two**
independent property candidates; F14/F27 now distinguish exact `date`,
ambiguous `reference` and future `occurrence` roles. F10's mutual event
remains **one candidate** but was misclassified `occurrence` instead of
`relationship`. The F14/F27 model spans are more informative, but the
current **narrow opt-in Core source-evidence pilots reject their alternative
anchoring/role inheritance** before writes; this does NOT prove a problem
with their underlying event segmentation. Preserve these real observed
outputs offline and review whether Core should accept equivalent proven
source spans rather than overconstraining GPT-6 to one handwritten template.
Router v1 remains inactive; focus on **F09/F10/F14/F27 only** until both
semantic type accuracy and Core-reviewed coverage pass. The remaining 23
approved design cases are deliberately deferred until this four-case gate
is settled. No DEV/PROD or vault changes.

**F27 exact sequential-source Core pilot (2026-10-10):** The two separate
conversation facts for `hablé con Eric y después con Luis` now also pass a
real (fake-model) semantic Core compilation, source-before-write candidate
coverage, per-fact canonical reference verification, two true Markdown
backlinks, durable pending state and a guarded `Con Luis` continuation.
Core checks the explicit "después" distinction and two independent dated
atomic facts; F14 continues using the different one-event/two-participant
contract. Incorrect order/name/helper/time and invented pending pronoun scope
fail closed. This is a narrow regression with injected frozen model responses;
no provider-quality proof or DEV activation is claimed.

**Request-wide F14/F27 continuation safety (2026-10-10):** Added an
opt-in before-any-action Core guard for the selected `Con Luis` continuation.
A single source-anchored cinema fact, the original `mañana` date and one
existing canonical helper are required; extra RequestPlan actions and
mismatched event/date are rejected without writing. Last-moment identity
checks remain intact. This is a narrow disposable-vault pilot with synthetic
planner outputs, not general semantic certification or live activation.

## Current functional work — explainable clarification

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

[Semantic set resolution and evidence](semantic-set-resolution-and-evidence.md) is complete and merged in
PR #142. The approved simplification keeps ordinary single-topic answers, matching Notes as objects via
`presentation_intent=note_set`, and canonical-fact collections via `RetrieveAction.result_shape=collection`
distinct. The planner preserves a lossless query while Core owns bounded evidence, collection discovery,
grounding, completeness, ambiguity, stale checks, and fail-closed behavior; no generic Note/type,
automatic entity promotion, recursive graph inference, or keyword/domain router is introduced. The narrow
clarification-continuation slice (#137) is included; broader staged/multi-action continuation remains deferred.

The focused Luna/low live-regression gate for PR #142 is **closed**. Collection-shape, Note-set/singular,
linked-selection, write, clarification, escalation, and mixed-action sentinels now have passing evidence on
the final behavior-bearing HEAD `8f99a1197cfaaf7c5a640f1749926fa8a2155a96`; the remaining five closeout
sentinels passed 5/5, and a one-call SM01 diagnostic reproduced the previously reviewed valid plan. Two earlier
DNS-resolution failures were pre-provider infrastructure evidence only. A real Structured Outputs/Core mismatch
was also closed by requiring non-empty `WriteAction.units`, and bounded write diagnostics were refined without
relaxing validation. No additional Luna calls are required. Detailed retry/evidence history is retained in the PR
and benchmark artifacts rather than duplicated here.

Real DEV smoke after #142 exposed #140/#137 behavior: duplicate self facts could falsely appear
ambiguous, singular multi-member facts did not yield safe identity choices, and collection
planning dropped authenticated-self scope. The observed 22-source/55-fact/13,162-byte DEV scan
stayed within its former bounds; those limits were a separate vault-size cliff.
The [corrective architecture challenge](semantic-set-resolution-and-evidence.md#corrective-architecture-challenge-after-real-dev-evidence-140137)
revised the contract and is implemented on `fix/semantic-self-clarification`: minimal
`self | query` collection subject, Core-bound self evidence, exact relational target
deduplication, reuse of existing pending identity clarification, bounded progressive canonical
scanning, and distinct user-safe failure reasons. Deterministic Core/runtime coverage is complete.
The frozen v8 Luna/low gate ran once at `32585c47bab0a90159ce2fc05339aa1c1c22ce5b` and stopped
fail-fast after two calls: SSET01 passed; SSET02 failed because it emitted
`collection_subject=self` instead of the unchanged required `query`. The two-row immutable artifact
has SHA-256 `cf4b5b9295f35149840105cca8fc02a2fae6abc066bdfb3307a83123bc7fe35e`. The frozen v9 gate
then ran once at `e86de53dabdd8b628d7918fdda647f629d4862a1`: SSET01 through REG02 passed, including
SSET02 as `collection_subject=query`, then NOTE01 failed closed at `RETRIEVE_ACTION` /
`SELECTION_MODE_CONFLICT`. Its seven-row immutable artifact has SHA-256
`edaeaa65885d7340efb821a9013aaac367031fa60ad4066d9b31ebe453762bcf`; neither run reached selector
rows, retried, or used Sol. Core validation remains fail closed. The current structural correction
partitions `collection_subject` by retrieval shape in the provider schema and prepares frozen v10,
which reuses all 21 planner and 4 selector rows with a 25-call maximum and `$0.41144` conservative
no-cache ceiling. V10 requires separate Luna/low authorization before production model-facing
adoption.

[UI polish + Notes editing lite](ui-polish-notes-editing-lite.md) merged in PR #144, the
Luna-only Semantic WRITE compiler simplification merged in PR #147, and Explainable Clarification UX
merged in PR #148. The clarification phase is complete: the user validated the candidate/evidence UI
and natural-language continuation in isolated DEV, deterministic validation remained green, and the
final reviewed Luna/low planner evidence fixed the blocking ownership regression while retaining the
approved fail-closed degradations. PROD has not been promoted to #148.

[Notes grouped browsing UX](notes-grouped-browsing.md) is implemented and user-validated in isolated
DEV. Runtime-composed Notes capabilities own the visible type descriptions/properties; ordinary
feed/local browsing has independent bounded type cursors, while intelligent and historical result
sets preserve one global deterministic authority. Calendar Day remains outside Notes-visible groups.
The follow-on [Calendar rich month view](calendar-rich-month-view.md) replaces dot-only monthly
indicators with a bounded four-row semantic preview while preserving one month request and the
existing Day navigation boundary; compact/expanded month modes and per-Day `Ver más` are now
user-validated in isolated DEV. The next [Calendar multi-day schedule view](calendar-multiday-schedule-view.md)
adds a read-only 1/3/7-day hourly projection over existing exact Task planning coordinates and semantic
fact anchors, with window-sized swipe navigation; implementation is complete and isolated-DEV mobile
review is next.

[Temporal Foundation v1](temporal-foundation-v1.md) is provider-free complete. Calendar v0 and
Application Boundary + Router v0 have completed their earlier focused live gates and isolated-DEV
adoption, and the shared Temporal contract now adds timezone-validated `EXACT_DATETIME` without
introducing app-to-app routing. The bounded Journal/Temporal convergence follow-up remains the active
closeout before Tasks. Router v6 first passed its 17/17 successor matrix, Temporal passed 5/6 with the
sole missing-offset result subsequently canonicalized deterministically, and the `complete_set`
fact-reference correction then passed its consumed Core successor gate 4/4 at `$0.01135904` regional
estimated cost. A later disposable full-runtime user-path check intentionally went beyond those isolated
model gates and found two additional integration/model-boundary issues: the exact Ana/Luis request
completed correctly but Router did not split it on that call, while `Mañana a las 15:35 viene el
fontanero.` failed closed with zero mutation after Luna semantic-write validation and bounded Sol
fallback. Review found provider schemas still admitted managed Calendar Day shapes that deterministic
Core rejects. The candidate now aligns Luna's Day operation branch with Core's `one + record +
facts-only` rule and constrains Sol Day selection to trusted exact dates. The explicitly authorized
eight-call Router/Core successor was then consumed with zero retries/mutations at `$0.00932448`:
Core passed 3/3, including the exact-time fontanero case, while Router passed 3/5. The three repeated
Ana/Luis splits all passed; the two failures were the dependent no-split sentinels (shared temporal
scope and ellipsis/specialization). No live retry was performed. Router's current candidate therefore
strengthens exact-span semantic completeness and selects specialized capabilities from requested
lifecycle semantics rather than surface resemblance, without phrase-specific rules. Disposable
provider-free user paths now preserve Ana/Luis as two Day writes and render exact Day time canonically
as `15:35 — ...`; the full deterministic suite is green. **Tasks** remains next after a small isolated-
DEV user-visible validation of this post-gate Router revision.

```text
20.0  consumer contract + architecture challenge             ✅ complete
20.1A offline grounded-answerer benchmark preparation        ✅ complete
20.1B focused live answerer model evidence                    ✅ complete
20.2A mobile web source + offline deterministic checks        ✅ complete
20.2B real n8n serving + Chrome Android validation            ✅ complete
20.2C planner incident hardening + focused live gate          ✅ complete
20.2D Luna-first planner experiment preparation               ✅ complete
20.2E Luna prompt-parity + atomicity validation               ✅ complete
20.2F Luna-first semantic planning + same-contract Sol fallback   ✅ complete
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
Semantic WRITE intent/Core compiler simplification                ✅ complete — v8 accepted at 12/13; GPT-5.6 Luna retained
Semantic set resolution and evidence                             ✅ merged in PR #142
Semantic self scope and clarification correction                   ✅ complete
UI polish + Notes editing lite                                     ✅ merged in PR #144
Explainable Clarification UX                                       ✅ merged in PR #148; DEV validated
Temporal Foundation + Calendar v0                                  ✅ Attempt 8 Calendar low live gate 10/10; DEV adopted
Application Boundary + Router v0                                    ✅ Attempt 5 Router live gate 8/8; DEV adopted
Temporal Foundation v1 — shared date/date-time contract              ✅ provider-free complete; Calendar artifacts unchanged
Journal/Temporal convergence follow-up                              ➡️ isolated DEV user-visible validation pending
Tasks — first lifecycle-heavy domain application                  ⬜ after DEV user-path recheck
Notes grouped browsing UX                                         ✅ isolated DEV user-validated; future authoring controls deferred
Calendar rich month view                                          ✅ isolated DEV user-validated
Calendar multi-day 1/3/7 schedule view                            ➡️ implementation complete; isolated DEV mobile review next
Events — timed occurrence semantics on Calendar                   ⬜ after Tasks
Reminders — lower-level delivery for Tasks / Events               ⬜ planned as needed
Maintainability checkpoint — bounded cleanup after calendar path  ⬜ planned
Projects — compose over Tasks                                     ⬜ planned after checkpoint
```

Merged PR #147 contains the first reversible offline Luna-only semantic WRITE frontend.
Provider-free assertions keep Sol's 25,474-byte prompt and 47,418-byte provider schema identical to
baseline while Luna compiles each ordered semantic write action immediately into the existing
`WriteAction` / `RequestPlan` boundary. After the v6 regression review, the teaching data is restored
semantically to the last stable checkpoint that passed SWR01-SWR07. The current Luna prompt is 32,281
bytes (from 32,076), the whole schema is 18,539 bytes (from 22,521), and the WRITE branch is 3,378
bytes (from 7,343); these are size measurements only, not latency evidence. Historical v8 assets remain
immutable and old-contract v9 is retired unexecuted. The authorized v6 gate passed SWR01-SWR03 but
regressed on SWR04 after example retuning. Rather than continue that non-monotonic tuning, frontend-v7
is retired unexecuted. Offline frontend-v8 restores the known-best teaching semantics and changes only
the semantic source vocabulary: provider-facing `EXISTING_DESCRIPTION` becomes `SOURCE_DESCRIPTION`.
This no longer asks Luna to assert source existence; it describes the user-supplied source and Core
must ground it as existing canonical evidence or clarify. The same 13-case gate collected the complete matrix in one authorized run: **12/13 passed**. SWR08 and SWR10 passed; only SWR07 failed because Luna kept the full qualified participant description but omitted its source-bounded candidate scope. This makes the remaining weakness explicit rather than hiding later results behind fail-fast. The v8 lineage is now permanently consumed at `MAX_COST_USD=$0.00`. The project accepts that bounded degradation rather than adding case-specific prompt complexity. A frozen model-only comparison then ran the identical matrix on `gpt-6-luna` / low: **11/13 passed**. GPT-6 Luna fixed SWR07 but regressed SWR08 and SWR10 by dropping event-source bounds on fact references. Its estimated cost was `$0.00419596` versus `$0.00912232` for GPT-5.6 Luna, but the planner retains **GPT-5.6 Luna** because it is more accurate on the frozen regression matrix.

Earlier latency observations motivate P1 but do not predetermine its bottleneck or authorize a fast path.

### 20.1B — answerer adoption gate

Complete. Frozen live evidence selected the inexpensive grounded answerer without weakening the bounded evidence contract. See [Phase 20.1 grounded-answerer benchmark](phase-20-1-grounded-answerer-benchmark.md).

### 20.2B — real browser integration

Complete. The checked-in `odyssey_web/` surface is served through the private n8n-facing product boundary. Raspberry-backed integration evidence covers the narrow request/response routes, and the physical Chrome/Android checkpoint covers the mobile UI, bounded delivery failure, restored controls, and explicit same-`request_id` Retry behavior.

### 20.2C — planner incident hardening

Complete. The production planner has explicit clarification, a bounded output envelope, zero automatic retries, and bounded post-parse validation diagnostics. See [Planner incident hardening](planner-incident-hardening.md).

### 20.2D–20.2F — Luna-first planner adoption

Complete. Luna/low is the production first pass. Safe PLAN/CLARIFY returns directly; structured fail-closed may invoke one bounded Sol/low fallback through the **same semantic prompt/schema/compiler**, so the fallback differs only by model rather than by planner language. Separate provider-call evidence preserves the real Luna/Sol usage split. See [Phase 20.2F — Luna-first production planning](phase-20-2f-luna-first-production.md).

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
Semantic set resolution and evidence                  ✅ merged in PR #142
Explainable Clarification UX                           ✅ merged in PR #148
        |
        v
Temporal Foundation + Calendar v0                     ✅ Attempt 8 Calendar low live gate 10/10; DEV adopted
        |
        v
Application Boundary + Router v0                     ✅ Attempt 5 Router 8/8 + Calendar Attempt 8 10/10; DEV adopted
        |
        v
Temporal Foundation v1                               ✅ shared EXACT_DATETIME contract complete
        |
        v
Tasks — first lifecycle-heavy domain application
        |
        v
Notes grouped browsing UX
        |
        v
Calendar rich month view
        |
        v
Calendar 1/3/7-day read-only schedule projection
        |
        v
Events — timed occurrence semantics on Calendar
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

The approved order now starts with **Temporal Foundation + Calendar v0**, followed by the small
**Temporal Foundation v1** extension: date/Day identity and Calendar-managed daily capture remain
lower-level behavior, while the shared normalized contract now also supports timezone-validated exact
date-times for Tasks and later Events. **Tasks** remains the first lifecycle-heavy domain application.
**Events** follows Tasks and projects timed occurrences onto the same Calendar surface. **Reminders**
should provide only the lower-level notification/delivery semantics Tasks and Events actually need; it
must not collapse tasks and events into one model. **Projects** remains a committed consumer of Tasks
but can follow the calendar path and the bounded maintainability checkpoint rather than blocking
Events. See [Temporal Foundation + Calendar v0](temporal-foundation-calendar-v0.md),
[Temporal Foundation v1](temporal-foundation-v1.md), and
[Future Events / Calendar capability](future-events-calendar.md).

Do not build a generic plugin platform before Tasks proves what the common application contract actually needs.

Planner/model extensibility must stay configuration-driven where semantics are already supported. The current planner derives note-type/property capabilities from `config/note-schema.json`; downstream model boundaries are generic with respect to concrete note types. The remaining application gap is executable manifest/registry routing for `DelegateAction`, not hard-coded app selection in the base planner. See [Architecture Overview](overview.md#configuration-driven-model-boundaries), [Future Odyssey product interface](future-product-interface.md#application-interaction--automatic-by-default-explicit-when-useful), [Future Extension Points](future-extension-points.md), [Future Events / Calendar capability](future-events-calendar.md), and [Odyssey Platform Direction](odyssey-platform-direction.md).

Once application work becomes repetitive, evaluate a bounded **agent-assisted delivery loop**: human + assistant approve a feature contract and validation criteria, an implementation agent works only in isolated DEV, deterministic checks run first, an independent validation agent reviews from fresh context, and only a final evidence-backed PR returns to the human for acceptance. This automation should not be introduced during Core architecture work and must never autonomously merge/promote production. Detailed guardrails and scheduling direction live in [Future Extension Points](future-extension-points.md#agent-assisted-application-delivery).

### Maintainability checkpoint after the calendar/application foundation

Maintainability is a continuous acceptance concern during every phase, but Odyssey should not pause
useful product work now for speculative restructuring. The near-term priority is the approved Temporal Foundation + Calendar v0 plus the bounded Temporal v1 date-time extension, then Tasks and Events with the minimum Reminder semantics those capabilities need.

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
- 💡 **Notes authoring and schema coaching:** grouped Notes should eventually support per-type Note creation, structured type/property editing with optional bounded conversational help, and manual editing of user-editable Note properties while keeping system provenance/identity and application-owned lifecycle fields protected. See [Future Odyssey product interface](future-product-interface.md#ui-4--safe-note-editing).
- 💡 **Product-wide localization:** a future language switch must translate the complete interface and onboarding/help copy—including type/property presentation—without changing canonical schema semantics or stored knowledge. See [Future Odyssey product interface](future-product-interface.md#deferred-product-decisions).
- 💡 **Direct Markdown/Obsidian edit ingestion:** eventually recognize authorized external edits, avoid self-trigger loops, validate only required normalization, refresh derived state, and audit accepted changes.
- 💡 **Structured analytics:** deterministic counts/sums/grouping over rebuildable structured/index data; do not load the whole vault into an LLM for arithmetic.
- 💡 **Agent-assisted app delivery:** after application work becomes routine, queue only human-approved feature contracts and let bounded implementation/validation agents work in isolated DEV with deterministic gates, explicit budgets, no autonomous merge/promotion, and final human acceptance. See [Future Extension Points](future-extension-points.md#agent-assisted-application-delivery).
- 🔄 **Cost-aware model routing:** Luna-first production planning and Luna/medium contextual reasoning are active; retain bounded Sol fallback only where the validated production contract requires it and continue optimizing from measured telemetry rather than assumption.
- 💡 **Proactive resurfacing:** non-disruptive reminders/context suggestions only after direct usage demonstrates value.
- 💡 **Performance/index optimization:** optimize from measurements, not anticipated scale.

## Roadmap rule

This file records **current status and intended sequencing**, not every implementation detail. When a phase completes, update the status here and leave its detailed contract/evidence in the phase document, ADR, tests, and benchmark records. Do not duplicate those historical narratives back into the roadmap.
