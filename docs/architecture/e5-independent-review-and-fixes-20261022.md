# E5 — independent final review and reproducible repairs (22 Oct 2026)

## Scope and independence

One external Codex read-only GPT-6 Sol/medium audit inspected pinned E5 snapshot `2c9404d65ce9df073436a3cab427d1c327c64da2` (deployed E5 code `18de992b648c418b4374d1c4ac395f4b18bb6c81`) against E4 baseline `7b092663d4164d9e87b31568fedba6d4cfb101af`. Audit job: `../.odyssey-agent-runs/e5-final-independent-review-20261022`. Report SHA-256: `619ea90428dff6b215a3d30f900b2dd6f9b234d5f936e15b9597555b56a8e50a`. The reviewer was not the code author, had read-only sandbox, did not deploy or alter the repository, and returned **FAIL**, not PASS.

## Two reproduced blocking findings

1. **Wrong dated cancellation.** `execute_event_candidate()` identified an Event by name but ignored the date mentioned in a CANCEL command. With an Excursión scheduled for Monday, "Cancela Excursión del viernes" could cancel that Monday Event. Reproduction in `tests/apps/events/test_e5_independent_audit_findings.py`.
2. **False multiday reschedule.** `bound_occurrence()` used model `START` and `END` mentions of an UPDATE as an interval, instead of an old-date/new-date move. "Mueve Teatro del martes al jueves" could change a one-day Event into a Tuesday–Thursday Event, including when Temporal condensed the expression into a `DATE_RANGE`.

Before repair the new audit regression set recorded **7 failures, 1 pass**. After repair it records **10/10 PASS**. Scoped Events tests reported **35 PASS**. The canonical shared Writer/E3, permission and replay boundary are reused unchanged.

## Corrected source-bound contracts

- CANCEL with an explicit date or clock must resolve it through shared Temporal; the exact Event's canonical date/time must match before the E3 mutation gate. Missing or contradictory evidence returns `needs_attention` without writing. A dated single occurrence cannot accidentally cancel an entire weekly recurrence or a different multiday Event. Undated explicit series cancellation continues to use exact-name resolution and E3 revision/hash.
- UPDATE understands explicit source-quoted `ORIGINAL_DATE` and `NEW_DATE` roles; Temporal must independently resolve both, and the original date must match the selected canonical Event. `START` + `END` and ambiguous compressed date ranges cannot be treated as origin/destination; they fail closed rather than fabricating a span.
- Source model prompt/provider schema now explicitly distinguishes creation intervals from reschedule origin/destination, version `e5_event_intent_v3`.
- A separate synthetic read-only **real GPT + Temporal** run confirmed `CANCEL` quoting `viernes 30 de octubre de 2026` as DATE and `UPDATE` quoting 27 October as ORIGINAL_DATE and 29 October as NEW_DATE. Both returned normalized Temporal EXACT_DATE proof, **2/2 PASS**.

## Acceptance gate and outstanding evidence

The corrected local branch passed **1,725 Python + 181 JavaScript + 7 subtests**, Ruff and diff checks. Existing E5 CRUD+Calendar+replay regression remains green.

**The original independent auditor's verdict remains historically FAIL.** These repairs do not rewrite that verdict or claim a second independent PASS. The final rollout gate is a single synthetic DEV real n8n GPT → E3 Writer → Markdown → Calendar readback of both dated cancellation and original/new-date rescheduling, plus byte-identical replay. Do not promote to PROD or declare post-audit DEV acceptance before that gate is complete. Existing PROD is out of scope. No new four-role audit loop is authorized.
