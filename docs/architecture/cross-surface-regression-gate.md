# Cross-surface regression gate — Core / Tasks / Work Sessions / UI / chat

Current check: **530 pytest PASS over 42 unique files / 9 contract groups and 168 Node PASS**, and full Python suite **3455 PASS / 80 SKIP / same 10 historical failures**, with no provider credentials forwarded. It is a reusable *deterministic* safety gate; the fresh live-model battery of 17 still has a false-negative Core/Planner review. The gate deliberately cannot certify natural-language Work Session/subtask routing, real browser-to-n8n, mixed multi-App crash recovery or semantic near-duplicate facts.

Status: **experimental adoption gate, NOT product E2E approval**. Maintainer entry point: `scripts/odyssey_cross_surface_gate.py`. Evidence remains reproducible and isolated; do not use personal DEV/PROD notes.

## One-command standard check

From the repository root, with the development virtualenv available:

```bash
PYTHONPATH=. .venv/bin/python scripts/odyssey_cross_surface_gate.py \
  --output /tmp/odyssey-cross-surface-regression.json
```

GitHub CI now executes this gate on PRs and pushes to main **before** the full Python suite, so historic frozen benchmark failures cannot conceal a new E2/E3 regression.

Use `--list` to see exact tests, or `--group work_sessions_shared` / `--group task_chat_core` for fast diagnosis. The default executes every group with real pytest, then the actual JavaScript/Node client and n8n-source tests. A missing file, failed pytest/Node test, or absent test summary is **BLOCKED**, not a misleading PASS. A report includes source groups, collected test files, counts, exit codes, and an explicit `real_full_product_e2e: false`. Do not commit user data or test transcripts; do not infer a successful production deployment from this JSON.

## Required domain scenarios and what is actually certified

| Contract | Deterministic/isolated checks | Still requires real E2E |
|---|---|---|
| E2 entities, SELF, dates and pronouns | source-coverages, named identity, negative/conditional, family, multiple facts/dates, exact Markdown readback | provider variance with unseen messages; alias ambiguities and contextual continuation |
| Task chat → Core | captured authentic model responses, Task lifecycle and parent reference readback, no Day fallback | fresh real-model chat for CREATE/COMPLETE/UPDATE/PARENT_TASK with actual n8n/UI |
| Direct Task / subtasks | Core preflight, E3 revision/hash, child/parent backlinks, stale, duplicate delivery, parent closed | actual user clicks and browser UI integrity |
| Work Sessions chat-owned service ↔ UI | real shared `TaskWorkSessionService` + `CanonicalMutationGate`, start/stop/edit/add activity, replay and physical parity | fresh natural-language route and source grouping; scoped multi-App route currently rejects sessions |
| Work Session UI extended | real HTTP `/notes` activity add/edit/delete, stop, task completion and blocked restart | authenticated browser UI; DELETE session has no equivalent conversational capability |
| E3/recovery | same-request replay, collision refusal, lock, crash/postwrite/partial, actor boundary | n8n retries and multi-App crash reconciliation after actual write |
| Canonical graph/index | links/backlinks against Markdown, readback, no phantom alias/SELF | real generated embeddings, larger vault loads and CPU/RAM on the Pi |
| Web/n8n | browser client validators and real n8n mapping source exercised locally | real webhook, authenticated browser and donut/stages/graph progression |

Tests are **layer-specific** and are not substituted for one another. A test injecting `TaskInterpretation` is not a successful natural-language interpretation; a saved genuine provider output is not a fresh GPT response; a real TCP localhost test is not a browser/n8n execution. For major architecture changes run this gate, the full pytest suite, Node, and a separate authorized real-LLM/end-to-end pilot. Previously existing full-suite red tests must be recorded individually, not silently skipped or reported as clean.

## Explicit architectural debts (not a claim of no hardcoding)

1. `odyssey_core/candidate_sequential_contacts.py` is a phrase-shape-specific legacy guard still called by `candidate_attribution.py` and `candidate_coverage.py`. Removing it without protecting older flows would be unsafe. Keep it quarantined; do not copy into the new whole-source Core route.
2. `odyssey_apps/tasks/planning.py`'s `TaskCorePlanner` inspects/manipulates generic `RequestPlan`, `WriteAction` and `KnowledgeUnit` despite the new App-specialization invariant in `AGENTS.md`. Existing tests establish compatibility, **not architectural convergence**. Replace only under a separately verified migration.
3. The new experimental P4 light-router implementation is still in `benchmarks/`, not a Core-owned production composition, so its demonstrated facts do not prove actual chat compatibility.
4. `execute_scoped_tasks` explicitly rejects Work Session operations. Old routed Tasks supports `START/STOP/EDIT/ADD_WORK_SESSION_ACTIVITY` through `TaskWorkSessionService`; deletion/edit/delete of individual activities is currently direct UI only. Natural-language subtask semantics have a different entry from `task_subtask_create` UI, even though both reach canonical Core/E3 mechanics.
5. Readback and route selection in the P4 acceptance *harness* necessarily name cases and expected outputs. Such test fixtures must never become production `if source contains ...` rules.

## P4 product acceptance still BLOCKED

Before asking the user to manually test the new route: introduce the whole-source Router/Planner/review contracts into production-owned modules with opt-in and no imports from `benchmarks`; handle mixed Core/Tasks/Work Sessions with typed capability ownership, idempotency and safe partial completion; test browser → n8n → runtime → fresh model → Markdown → n8n → browser with isolated user context. Include 1/3/5/many facts, pronouns, omitted subjects, different task titles, parent/subtask references, multiple sessions, invalid dates, requests both approved and rejected, stale revisions, restart/replay and mixed-language requests. Validate actual backlinked Markdown, graph and donut, response persistence and CPU/RAM/index work on Raspberry. Any failed required case blocks activation; do not rewrite the benchmark oracle to get green.

**Safety:** Never deploy or mutate DEV/PROD data as a side effect of running this gate. The archived chat recovery dry-run operates only on a clone and is NOT permission to restore personal conversations.

## Product P4 opt-in regression (16 October 2026)

`tests/runtime/test_whole_source_light_product_p4.py` is now part of the offline cross-surface CI gate. Product source is `odyssey_runtime/whole_source_light.py`, its model contract and Core compiler/readback are product-owned; for P4 Task CREATE, `RequestPlan` construction now stays strictly in `odyssey_core/whole_source_compiler.py` rather than calling legacy App `TaskCorePlanner`, with the Task-specific `TaskLifecycleGuard` still applied and have NO import of the PoC `benchmarks` package. The product path has a strict default-off flag, trusted SELF, mixed Task CREATE / Task-only source-scope reviewers, E3 at-most-once claim, canonical Writer, independent speaker reviews, bounded progress stages and full physical readback. The test corpus uses frozen genuine past provider outputs; real fresh-model proof is separate through explicitly opted-in `scripts/p4_product_live_isolated.py`, which uses disposable Notes and real localhost HTTP.

Release blockers remain explicit: P4 does not yet support general Work Session + Core mixed execution, genuine Task/subtask equivalence in every chat route, relationship-bound family facts in the new planner, semantic paraphrase no-ops, real n8n+authenticated browser coverage, CPU latency on real embeddings or interrupted-claim automatic reconciliation. No result of the offline gate or isolated product HTTP is treated as a passing complete product E2E. Python synthetic-scale measurements that rebuild indexes completely are upper bounds for those fixtures, NOT claims about production incremental refresh.

## 16-10-2026 concrete exercise results

Separate, user-authorized read-only model check: `ODYSSEY_APPROVE_LIGHT_POC=1 python -m benchmarks.application_router.light_router_poc_20261016.p4_tasks_nl_intent_live_probe` executes 10 safe synthetic Task/Work Session utterances on the actual model (GPT-6 low) without any Writer or vault. Last result **10/10 correct operation classification** including one PARENT_TASK; this **does not close** the chat light-router scoped Work Session support gap. This paid probe is explicitly excluded from ordinary offline CI.


- Repeated 17 fresh messages through isolated real HTTP/GPT: 11 completed, 6 needs_attention (5 conservative expected, one genuinely overblocked third-person statement). Replay and Markdown inspected; **not a passing P4 acceptance**.
- `NO_CHANGE` on an existing Day with a newly created Task is a valid mixed result. An existing SELF preference with unchanged Markdown is also valid **only** when its prior marked fact, owner, exact text and links are read back. The new P4 physical oracle refuses arbitrary `completed` without those proofs. Paraphrased near-duplicates may still be introduced and remain a release blocker.
- Real `/notes` HTTP isolated: parent → subtask → Work Session start → activity add/edit/delete → stop → child Task complete; repeated deliveries, a reused request ID across operations, malformed transport, closed task and inconsistent timestamps; no actual user notes modified.
- 12 distinct subtask titles and the alternate chat-domain service path preserve the same canonical Work Session lifecycle. This proves shared domain mechanics, not the independent model's interpretation.

The gate should run after every architectural change and before promoting a branch to DEV, **followed by separate fresh-model and authenticated browser/n8n tests**. If a case is genuinely ambiguous, document `needs_attention` rather than forcing a write. Never allow an unrelated test update to suppress a required failure.

## N-dependent ordered execution and Tasks domain prewrite veto (branch-only, 17 October 2026)

`tests/runtime/test_p4_dependent_n_graph_execution.py` and `tests/apps/tasks/test_batch_preflight.py` now cover real canonical Core/Tasks writes in **three verified dependent scopes**, E3 immutable operation manifest and same-ID replay, source drift partial and postwrite crash blocked without retry, and fail-closed veto of an unrepresented Work Session START→STOP dependency in a four-scope route. Provider-frozen successes are NOT promoted to GPT acceptance: 0/3 new real-model graph-audit samples passed end-to-end, as recorded in [the stage report](p4-dependent-n-execution-gate-20261017.md). **Final offline gate 896 Python +168 Node PASS; global Python 3799 PASS/80 SKIP/52 subtests PASS with the same 10 frozen benchmark/pricing failures.** The final adapter-missing guard landed after global and passed 43 focused tests plus the final cross-surface gate. Ledger 17 invariants/35 required anchored tests. No DEV or PROD deploy; browser+n8n remain untested for N.

## Per-edge canonical N:M evidence (branch-only, 17 October 2026)

`tests/core/test_p4_canonical_group_handoff.py` exercises physical Core Writer Markdown evidence: N source groups → one downstream group, one source → N consumers, and a **single** Core WriteAction that materializes two distinct wikilinks and successfully binds each to its own reviewed source mention. Any missing/ambiguous link, altered reference, soft-delete, partial predecessor, stale source or target cancels the whole handoff before the consumer. The handoff is read-only and reuses Core's existing dependent evidence freshness and preflight guards. The stage passed **874 Python +168 Node** cross-surface tests and full **3778 Python PASS /80 SKIP /unchanged 10 historical benchmark-pricing FAIL**, with 52 subtests PASS and acceptance 17/34. It does **not** enable execution of dependent N:M workflows nor authorize DEV deployment. See [the P4 canonical-edge report](p4-nm-canonical-edge-proof-20261017.md).

## N:M source graph and durable E3 operation journal (branch-only, 17 October 2026)

`tests/core/test_p4_dependent_group_graph.py` checks 2–16 exact-source groups and independently corroborated N:M predecessor edges, but never asserts canonical Note authority or executes the still-blocked 3+ dependent chain. `tests/runtime/test_p4_operation_manifest.py` checks durable per-delivery hash-only plans and ordered immutable observed App outcomes in the same actor-local E3 state. The product factory records both 1→1 dependent and N-independent paths. It conservatively aborts if manifest creation fails before WRITE, and keeps the original claim unresolved if the process dies after a physical Task write but before its operation observation. Neither record can grant postwrite recovery without an immutable terminal receipt.

New cross-surface gate **860 Python + 168 Node PASS**, global **3764 PASS, 80 SKIP, unchanged ten historical frozen benchmark/pricing failures**; acceptance ledger 17 invariants/31 anchors, with two new blocking requirements. **No new model-facing prompts or fresh GPT samples in this block**, no browser/n8n evidence and no DEV authorization. See [the stage report](p4-nm-source-graph-e3-operation-manifest-20261017.md).

## Independent N-scope and E3 confirmed-claim gate (branch-only, 17 October 2026)

The opt-in whole-source path now verifies the Router's exact ordered N scopes against its independent source partition before any write. It preinterprets **all** independent Tasks/Temporal scopes before the first Core write, then executes those prepared interpretations through the standard Task/Core services. A later Core scope refreshes only the previously affected IDs via strict incremental indices; unrelated drift yields a durable `partial`, not a whole-index rebuild or blind retry. New tests cover three independent operations with physical SELF and Work Session readback, a four-group last-Task veto with **zero** writes, conflicting Router topology and a forced midmessage refresh failure. E3 reconciliation removes a stale claim **only** after validating a complete immutable receipt; missing receipts remain blocked even if Markdown might already have been written. Tampered fingerprints and symlinks fail closed.

This gate passed **833 Python and 168 Node** tests. A separate authorized fresh-GPT disposable-vault smoke passed **one Core→Tasks→Core** scenario with exact physical Markdown, one Work Session and unchanged E3 replay. The full Python suite finished with **3737 PASS, 80 SKIP, the exact same ten historical benchmark/pricing failures**, and 52 passing subtests. This is not complete real-model variance or browser→n8n product acceptance. Dependencies N:M and postwrite recovery without a receipt remain blocked. See [the stage report](p4-independent-nscopes-e3-claim-reconciliation-20261017.md).

## Dependent subtask title gate (branch-only, 17 October 2026)

`tests/runtime/test_p4_dependent_router_integrated.py` now covers the narrow Core→Task child path with a recorded normal-Core `RequestPlan`, real predecessor Core Writer, existing `TaskDirectMutationService.create_subtask`, physical parent/child Markdown readback and immutable E3 replay. It also rejects a duplicate/parent title, wrong Task type, extra fact or action, unavailable planner, stale/closed parent via the direct service, reviewer disagreement, unsupported multi-scope input, and a postwrite crash that retains the unresolved outer claim. `tests/runtime/test_p4_dependent_factory_product.py` verifies the production factory uses the existing GPT-5.6 Core planner seam plus `TaskCorePlanner`, not a subtask prompt.

Ruff on touched files, the focused 58-test set, the acceptance ledger, and the cross-surface gate have run in the repository development virtualenv: **822 Python + 168 Node PASS**. The full Python suite completed at 3725 PASS, 80 SKIP, 52 subtests PASS and the same ten historical frozen benchmark/pricing failures (before the additional postwrite-child-crash regression test); no new regressions. The final cross-surface gate runs that extra test. N:M remains rejected; no automatic E3 reconciliation was added. Fresh GPT-5.6 and authenticated browser→n8n→Markdown→UI evidence remain required.

Scale caveat: after switching the synthetic benchmark to the same incremental-index refresh boundary as production, one 1000-note request (fake model output and ConstantEmbedder) still took approximately 5.23 seconds locally, without full index rebuild. At 250 notes it took 1.33 seconds, at 20 notes 0.13 seconds. This suggests an O(N) read/validation bottleneck that must be measured and improved against larger real vaults BEFORE DEV, not explained away by 'index only' or hidden from the user. Results in `/tmp/odyssey-p4-product-scale-productionlike.log` on the Pi.

Post-P4 offline evidence: **545 Python + 168 Node PASS**, global **3470 Python PASS, 80 SKIP, same ten historical failures** (52 subtests pass). Tool output is on the Pi under `/tmp/odyssey-p4-final-offline-gate.log`, `/tmp/odyssey-p4-final-global.log` and `/tmp/odyssey-p4-final-strict-live.log`.

After strengthening the REAL-model live evaluator, success now requires the expected status (not just HTTP 200), exact per-delivery physical fact count, a Task created only in Task-creation scenarios, no mutation for negative sources, and byte-identical replay. A safe but overblocking `needs_attention` is **a failed positive case**. One fresh Core+Task execution did overblock, although subsequent strict fresh run passed all 5 cases. Model variance remains a deployment blocker. This is not a cumulative '100% success' claim.
