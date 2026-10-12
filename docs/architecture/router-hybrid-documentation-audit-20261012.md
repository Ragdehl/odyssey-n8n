# Router hybrid: documentation conflict audit — 2026-10-12

**Result:** 2026-10-12 hybrid interpretation grouping is the human-approved
**target**, not the currently deployed DEV/PROD implementation. This audit
updates documentation only. Previous code and model evidence remain unchanged.

## Canonical reading order for the next conversation

1. [AGENTS.md](../../AGENTS.md): standing instructions and explicit hybrid
   target decision.
2. [Functional roadmap](functional-roadmap.md): current implementation state,
   next adoption gates and unchanged model-version plan.
3. [Hybrid interpretation contract](router-hybrid-interpretation-contract.md):
   **single normative technical target**. Candidate, interpretation group
   and atomic fact/write are three separate granularities.
4. [ADR 0010](../decisions/0010-router-hybrid-interpretation-groups.md):
   user decision and rejected alternatives.
5. Old Router contracts and experiments remain historical evidence, not
   competing instructions to split each candidate into a separate Core call.

## Contradictions found and reconciled

| Source | Earlier conflicting requirement | Resolution |
| --- | --- | --- |
| `AGENTS.md` | Only group indivisible events/corrections; split separately writable facts; require a preceding Core write for inherited linguistic source | Replaced with bounded semantically dependent **interpretation groups**, separate source candidates/fact writes; Core-verified handoffs only when needed **between** groups |
| `functional-roadmap.md` | 2026-10-11 strictly per-unit dispatch was the approved next phase | Replaced with 2026-10-12 hybrid target and truthful 2/5 pilot evidence; older roadmap entries labeled historical |
| `router-unit-dispatch-contract.md` | Described the strict source-fragment design as authoritative | Added explicit supersession banner, preserving prior model observations and cross-group guards |
| `router-fact-units-v1.md` | 2026-10-11 “correction” instructed atomic Core calls | Added latest-authority banner before that older warning; retained historical design data and oracles |
| `router-scope-27-live-regression-20261011.md` | Considered most same-source groupings an architecture violation | Reframed as historical diagnosis under the former strict contract; measured outcomes unchanged |
| `router-dependent-route-continuity.md` | Dependency means a Core predecessor for every linguistic omission | Clarified same-group interpretation versus **cross-group** canonical proof |
| `router-parallel-preparation.md` | Older v0 routes were the unit of concurrent preparation | Future safe concurrency restricted to **independent interpretation groups**; existing code not claimed changed |
| `application-boundary-router-v0.md` | Historical partition heuristic could be mistaken for future hybrid compiler | Added explicit current-v0 / future-hybrid boundary and reference |
| `overview.md` | Did not identify the adopted Router direction | Added future-target pointer without altering current-runtime claims |
| `temporal-foundation-v1.md` | Earlier capability-local Temporal description could be read as excluding future group-level Temporal | Added a target-vs-historical scope note; preserved existing exact/unspecified fail-closed temporal semantics |
| `docs/decisions/README.md` | No permanent decision record | Indexed ADR 0010 |
| `development-pipeline.md` | No preventive architecture supersession checklist | Added a repeatable coherence gate to prevent two simultaneous approved contracts |


## Unchanged safety and status

- Core is the identity, semantics and canonical Writer authority. Router
  candidates never directly authorize Note type, link, mutation or date.
- Full original message is Router input and read-only provenance, never a
  *second Core interpretation of unrelated sibling groups*.
- F06/F22 remain independent where their actions do not rely on one another.
  Ambiguous F14/F27 pronouns stay unresolved. A shared clock cannot silently
  be guessed; conditional/negative/cancelled statements cannot become
  confirmed occurrences by virtue of grouping.
- Earlier typed date/identity/event proofs are retained for **cross-group**
  continuity. Do not remove their tests or weaken current freshness guards.
- Core GPT-5.6 remains configured for the candidate work; GPT-6 model migration
  is separately deferred. No app/schema/DEV/PROD/n8n/personal vault changes.

## Pilot evidence and next code gates

Five genuine Temporal/Core model probes (using stored real Router outputs
and disposable test Notes) reported **2 complete**: F04 and F16;
**2 pending in Core**: F03 ambiguous `mis hijos` and F23 grouped-reference
coverage; **1 blocked by Temporal**: F21 `a las 18h` unresolved across
Monday/Wednesday. The 2/5 score is design evidence, NOT production readiness.
Five-probe estimated spend USD 0.0135635; cumulative USD 0.2789394 / 0.50.

The **next** phase implements bounded source grouping, candidate↔fact
coverage and safe partial outcomes, then targeted F03/F21/F23 repairs and
the 27-case regression; DEV/PROD promotion remains separately gated.

## Subsequent implementation checkpoint (2026-10-12; historical first pilot retained)

The five-probe **2/5 result above is the original measured observation**,
not the present feature-branch success count. After the opt-in hybrid
compiler was implemented, targeted grouped Core/Temporal fixes produced
**fresh real-model + independent reviewer + physical Markdown readback
successes for F03, F21 and F23**, in addition to earlier F04/F16.
Those narrowly scoped positive variants and their exact genuine responses
are frozen in `benchmarks/application_router/hybrid_grouped_v2/`.
F03 preserves an unverified complete-set participant group literally;
F21 validates two weekday-owned exact instants sharing one source clock;
F23 writes two independent positive reference-free project facts.
No DEV/PROD activation or broad negation/task/conditional/ambiguity guarantee
follows from these experiments. Estimated total experimental spend:
**USD 0.2951979 of USD 0.50** at this checkpoint.

## Prevention rule

Before any future architecture replacement, search active `AGENTS.md`,
roadmap, overview, routing contracts, ADRs and development runbooks for
conflicting “current/approved/must” statements. Replace governing passages,
mark older dated experiments **superseded** instead of deleting their
evidence, check Markdown relative links and preserve an explicit
**target vs implemented vs deployed** status. Do not allow a later historical
checkpoint to overrule a newer normative contract.
