# Odyssey P4 product — independent Core fact + existing Work Session mutation

## User-visible goal
Finish one **real Odyssey application** gap from the approved E1/E2/E3 roadmap, NOT more agent infrastructure. A message such as:
"Hoy hablé con Marta y terminé la sesión de trabajo de la tarea Atlas"
must preserve both independently authored actions:
1) Core safely records only the Core fact ("Hoy hablé con Marta") with validated actor/date/identity and physical Markdown readback.
2) Tasks safely closes exactly one pre-existing active Work Session of the named existing Task through the **canonical** Work Session service and E3 gates; no Task CREATE or independent Core copy of the session phrase.
The analogous ADD_WORK_SESSION_ACTIVITY case ("registré lo que hice en mi sesión X y conocí a Marta") should be supported IF it can use the exact same existing service; do not invent new mutation paths.

## Context / do not duplicate what already works
Read AGENTS.md, first active roadmap, application-extensibility-plan and p4-five-stage-evidence. Inspect existing `tests/runtime/test_p4_independent_mixed_scopes.py` (already proves independent Core + START_WORK_SESSION with E3 replay and UI), `tests/runtime/test_whole_source_light_product_p4.py` (existing safety veto preventing Work Sessions smuggled as Task CREATE), `odyssey_runtime/whole_source_light.py`, and Tasks session service. Choose one real **missing variant** (STOP or session activity update in a mixed independent Core+Tasks request). Avoid a redundant implementation if already supported. Reuse the existing dispatch/typed E2 provenance/Task service/Writer and `LocalDeliveryResultStore` rather than adding a second mutation engine.

## Hard acceptance
- Keep the full exact original source anchored in validated independent scopes; no fixed phrases/names/quantities. Unrelated Core fact and Work Session action each have their own canonical target and receipt, with exactly one Work Session mutation and no accidental new Task.
- Existing task & active session must be resolved authoritatively; missing/stale/ambiguous, stopped session, cross-actor or changed revision must fail closed before unsafe writes. No id guessing, no fake SELF or time, no special-casing "Marta" or "Atlas."
- End-to-end isolated product **runtime** test on disposable synthetic Markdown using the actual Core Writer + TaskWorkSessionService or its existing canonical adapter, with provider responses recorded exactly as needed: verify completed semantics, readback for both, replay same request ID with zero duplicate writes, plus negative tests for invalid session and fabricated identity. Do not call real actor vault. Preserve stable graph/flow and make clear recorded provider output is not a live-GPT E2E.
- If full mixed STOP cannot be implemented safely within strict scope, produce a genuine fail-closed contract/test improvement and return an explicit limitation; do not make a fake green, disable reviewers/gates, skip existing regression coverage or weaken protections.
- Focus scope to existing `odyssey_runtime/whole_source_light.py`, `odyssey_apps/tasks/` as needed, and new/focused existing tests in `tests/runtime/test_p4_independent_mixed_scopes.py`, `tests/runtime/test_whole_source_light_product_p4.py`, `tests/runtime/test_p4_taskonly_real_session_parity.py`, or one new nearby test. No changes to `scripts/odyssey_agent_cycle.py`, agent permissions/model policy, scripts/odyssey_cross_surface_gate.py, Cloudflare, deploy scripts, installed n8n, web frontend, app configuration, PROD or actual DEV.
- Do not update roadmap or docs from Builder: supervisor and maintainer own acceptance docs after review; only change code and tests.

## Independent product acceptance
Scope classification PRODUCT, normal risk; FOUR mandatory independent auditors Generality, Quality, Testing, Performance, real host cross-surface Python/JS acceptance ledger and Ruff. No product readiness claim from offline tests alone. A true authenticated browser → n8n → live GPT → Core Writer → Markdown → reload E2E is separate and STILL REQUIRED for deploying this feature to DEV. Exactly one round for this initial supervised execution, with a cumulative 300000 CLI-reported-token job cap and existing daily pacing. Stop safely on a blocking verdict, environmental limitation, memory or budget issue. Never merge/deploy/push automatically, never contact real user Notes or credentials.
