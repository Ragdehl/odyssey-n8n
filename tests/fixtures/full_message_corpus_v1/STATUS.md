# Odyssey: 27-message real-model E2E evaluation — 2026-10-11

Frozen full original-message test corpus (F01–F27), thirteen real-format synthetic canonical Notes and independent temporary vaults. No changes to personal Notes, DEV or PROD.

Every actual four-model pipeline response is saved privately, with provider-output-only regression snapshots under benchmarks/application_router/full_message_corpus_v1/. These are observations, not semantic correctness certification.

## First blocking boundary

| Stage | Cases | Count |
|---|---|---:|
| Completed and physically verified | F11 | 1 |
| Router source/dependencies | F02, F03 | 2 |
| Temporal | F04, F08, F09, F10, F12, F15, F16, F19, F21, F23, F25, F27 | 12 |
| Core planning/handoff | F07, F14, F26 | 3 |
| Core coverage/graph review | F01, F05, F06, F13, F17, F18, F20, F22, F24 | 9 |

## Individual results

| ID | Original source | First blocker | Observed reason | Calls | Notes written |
|---|---|---|---|---:|---:|
| F01 | Ayer fuimos con mi mujer y mis hijos a las tres por la tarde al parque y después fuimos al cine y hoy vamos a ir a un concierto. | Core coverage/graph review | CANDIDATE_COVERAGE_REVIEW_REQUIRED, no write (later readback-attempt error was harness-only) | 4 | 0 |
| F02 | Esta tarde mis hijos, mi mujer y yo iremos a merendar sobre las 16h, mañana iremos al parque y el domingo a las 11h a un vide-grenier. | Router source/dependencies | Inherited source role has no evidence in its predecessor chain | 1 | 0 |
| F03 | Mañana vamos con mis hijos de paseo al parque y luego iremos al cine. | Router source/dependencies | Fact candidate output lacks grounded source evidence | 1 | 0 |
| F04 | Mañana iremos al parque a las 12 y luego a las 18 iremos al cine. | Temporal | Temporal provider response was not completed | 2 | 0 |
| F05 | El viernes cenaremos con Ana en Toulouse y el sábado a las 10 con Luis en Albi. | Core coverage/graph review | CANDIDATE_COVERAGE_REVIEW_REQUIRED, no write (later readback-attempt error was harness-only) | 4 | 0 |
| F06 | Hoy vi a Ana y compré pan. | Core coverage/graph review | CANDIDATE_COVERAGE_REVIEW_REQUIRED, no write (later readback-attempt error was harness-only) | 4 | 0 |
| F07 | Hoy a las 15h veo a Bea y a las 17h a Luis. | Core planning/handoff | Luna semantic WRITE contains temporal wording/temporal evidence not supplied by Temporal | 3 | 0 |
| F08 | Mañana Marta irá al médico a las 10 y Luis al dentista a la misma hora. | Temporal | Temporal provider response was not completed | 2 | 0 |
| F09 | Marta y Luis viven en Lyon. | Temporal | Temporal wording must be non-empty | 2 | 0 |
| F10 | Marta y Luis se conocieron en Lyon. | Temporal | Temporal wording must be non-empty | 2 | 0 |
| F11 | Hoy compré pan y leche. | Completed and physically verified | persisted_and_read_back | 4 | 1 |
| F12 | Bea y mis hijos limpiaron el garaje y después montaron los muebles. | Temporal | Temporal provider response was not completed | 2 | 0 |
| F13 | Ayer hablé con Eric. Mañana iré al cine con él. Hoy compré pan. | Core coverage/graph review | CANDIDATE_COVERAGE_REVIEW_REQUIRED, no write (later readback-attempt error was harness-only) | 4 | 0 |
| F14 | Ayer hablé con Eric y Luis. Mañana iré al cine con él. | Core planning/handoff | planner must return a PlannerResult | 3 | 0 |
| F15 | Ayer mis hijos fueron al parque y Bea se quedó en casa; después yo preparé la cena. | Temporal | Temporal resolution is not an exact Core anchor | 2 | 0 |
| F16 | Ana compró entradas para el concierto y Luis también. | Temporal | Temporal wording must be non-empty | 2 | 0 |
| F17 | Ayer no vi ni a Ana ni a Luis. | Core coverage/graph review | CANDIDATE_COVERAGE_REVIEW_REQUIRED, no write (later readback-attempt error was harness-only) | 4 | 0 |
| F18 | Ayer no vi a Ana, pero sí hablé con Luis. | Core coverage/graph review | CANDIDATE_COVERAGE_REVIEW_REQUIRED, no write (later readback-attempt error was harness-only) | 4 | 0 |
| F19 | Mañana iremos al parque a las 11... no, mejor al cine a las 12. | Temporal | Temporal resolution is not an exact Core anchor | 2 | 0 |
| F20 | El sábado iremos al cine si no llueve, y si llueve nos quedaremos en casa. | Core coverage/graph review | CANDIDATE_COVERAGE_REVIEW_REQUIRED, no write (later readback-attempt error was harness-only) | 4 | 0 |
| F21 | La semana que viene tengo clase el lunes y el miércoles a las 18h. | Temporal | Temporal provider response was not completed | 2 | 0 |
| F22 | Hoy tengo que llamar a Ana y escribir a Luis; mañana preparar la factura. | Core coverage/graph review | CANDIDATE_COVERAGE_REVIEW_REQUIRED, no write (later readback-attempt error was harness-only) | 4 | 0 |
| F23 | El proyecto Odyssey tiene un fallo en Router y otro en Temporal. | Temporal | Temporal resolution is not an exact Core anchor | 2 | 0 |
| F24 | El coche está en el taller y mañana pasará la revisión. | Core coverage/graph review | CANDIDATE_COVERAGE_REVIEW_REQUIRED, no write (later readback-attempt error was harness-only) | 4 | 0 |
| F25 | La casa de Toulouse tiene humedad en el sótano y necesita reparar el tejado. | Temporal | Temporal provider response was not completed | 2 | 0 |
| F26 | El informe llegó ayer y hoy lo envié a Ana. | Core planning/handoff | Luna semantic WRITE omitted required temporal wording/temporal evidence | 3 | 0 |
| F27 | Ayer hablé con Eric y después con Luis. Mañana iré al cine con él. | Temporal | Temporal resolution is not an exact Core anchor | 2 | 0 |

## Provider cost and proof

* 27/27 real case attempts, 75 actual model responses, 5 incomplete.
* F11 completed all stages and persisted one Day fact with verified physical Markdown readback.
* All other cases wrote zero notes; blocked operations are not automatically semantic defects.
* Prior USD 0.056766; new estimated calls USD 0.0528623; cumulative USD 0.1096283 of the approved cumulative USD 0.25 (pinned standard rates; not billed statement).

## Next generic failure groups

1. Temporal (12): no-mention outputs rejected on no-time sources, provider output truncation, and approximate date/time not projected into the exact Core evidence contract. Preserve uncertainty, never invent a date.
2. Core coverage (9): independent graph reviewer and Core reject candidate-fact provenance. Compare frozen actual source candidates, planned facts, identities, shared N:M links; preserve fail-closed prewrite guard.
3. Core planning/handoff (3): 2 temporal-evidence mismatches, 1 unsupported plan outcome type; repair general Planner-to-application contract.
4. Router (2): unsafe inherited source role or ungrounded candidate. Do not invent missing evidence.

In the nine coverage-blocked runs, the live harness attempted readback even when Core returned needs_attention; its secondary ValueError is NOT the root cause. The real first failure is the Core prewrite coverage check, and no writes occurred. The next harness version skips readback for non-completed actions.

## Reproducible, unpaid proof

* pytest -q tests/runtime/test_full_message_recorded_provider_replay.py replays all 27 authentic model-output sequences through the existing adapters and disposable notes without provider access.
* pytest -q tests/runtime/test_full_message_corpus_regression.py checks the 27 original Router fixtures, original canonical test notes and prior saved F09/F10 Core plan writes and backlinks.
* Raw live receipts: /home/ragdehl/projects/odyssey-experimental-receipts/full-message-corpus-cap025/ (private, one-shot, no personal data).
