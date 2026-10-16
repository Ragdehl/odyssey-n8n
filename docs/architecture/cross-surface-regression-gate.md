# Cross-surface regression gate — Core / Tasks / Work Sessions / UI / chat

Current check: **529 pytest PASS over 42 unique files / 9 contract groups and 168 Node PASS**, and full Python suite **3454 PASS / 80 SKIP / same 10 historical failures**, with no provider credentials forwarded. It is a reusable *deterministic* safety gate; the fresh live-model battery of 17 still has a false-negative Core/Planner review. The gate deliberately cannot certify natural-language Work Session/subtask routing, real browser-to-n8n, mixed multi-App crash recovery or semantic near-duplicate facts.

Status: **experimental adoption gate, NOT product E2E approval**. Maintainer entry point: `scripts/odyssey_cross_surface_gate.py`. Evidence remains reproducible and isolated; do not use personal DEV/PROD notes.

## One-command standard check

From the repository root, with the development virtualenv available:

```bash
PYTHONPATH=. .venv/bin/python scripts/odyssey_cross_surface_gate.py \
  --output /tmp/odyssey-cross-surface-regression.json
```

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

## 16-10-2026 concrete exercise results

- Repeated 17 fresh messages through isolated real HTTP/GPT: 11 completed, 6 needs_attention (5 conservative expected, one genuinely overblocked third-person statement). Replay and Markdown inspected; **not a passing P4 acceptance**.
- `NO_CHANGE` on an existing Day with a newly created Task is a valid mixed result. An existing SELF preference with unchanged Markdown is also valid **only** when its prior marked fact, owner, exact text and links are read back. The new P4 physical oracle refuses arbitrary `completed` without those proofs. Paraphrased near-duplicates may still be introduced and remain a release blocker.
- Real `/notes` HTTP isolated: parent → subtask → Work Session start → activity add/edit/delete → stop → child Task complete; repeated deliveries, a reused request ID across operations, malformed transport, closed task and inconsistent timestamps; no actual user notes modified.
- 12 distinct subtask titles and the alternate chat-domain service path preserve the same canonical Work Session lifecycle. This proves shared domain mechanics, not the independent model's interpretation.

The gate should run after every architectural change and before promoting a branch to DEV, **followed by separate fresh-model and authenticated browser/n8n tests**. If a case is genuinely ambiguous, document `needs_attention` rather than forcing a write. Never allow an unrelated test update to suppress a required failure.
