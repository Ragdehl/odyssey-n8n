# Router v2 — reviewed four-case synthetic API gate

This separately reviewable source file is **not the previously rejected
inline shell evaluator**. It uses the existing production-shaped Router
request constructor and a committed snapshot, with a separate standalone
offline-by-default CLI. It is intended only for ordinary authorized
execution; a tool safety rejection must not be bypassed by another transport.

## Scope and controls

- Case order: F14, F27, F09, F10 (four synthetic messages only).
- Exactly 4 GPT-6 Luna/low Responses requests; strict Structured Outputs,
  `store=false`, fixed output cap 4096 and OpenAI SDK retries disabled.
- Conservative pre-call total reservation **$0.01181875**, below the user's
  previously authorized **$0.02** total budget. These are bounds, not invoices.
- No Core/Temporal provider calls, no Note writes, no connection to a user vault,
  no model/prompt/schema change or DEV/PROD deployment.
- A fixed request snapshot is verified before any live execution.
- `--live` **and** `ODYSSEY_ROUTER_V2_LIVE_APPROVED=1` must both be present.
  The Python module does not open any secrets file or load shell credentials.
  The authenticated execution environment must be independently authorized.
- Raw model JSON is persisted only for these predefined synthetic sentences
  and is *not* evidence of semantic correctness by itself.

## Safe offline checks (no key, network or provider usage)

```bash
cd /home/ragdehl/projects/odyssey-fact-candidates-v1
/home/ragdehl/projects/odyssey-dev/.venv/bin/python -m benchmarks.fact_candidate_v2_live.run_live
/home/ragdehl/projects/odyssey-dev/.venv/bin/python -m pytest -q tests/benchmarks/test_fact_candidate_v2_live_runner.py
```

Do not set the live flag until the exact command, account, environment,
authorization and limits have been reviewed. A normal approved execution saves
one time-stamped `results/*.json` artifact and prints only summary/usage. No
automatic retries; if any tool explicitly rejects the operation, stop rather
than repackaging it. Compare the observed F14/F27/F09/F10 responses with the
approved source-only contract before deciding whether Router is ready.

The PR must remain Draft until model semantics, independent Core verification
and the inherited historic release tests are resolved.

## Proposed Router prompt revision v2 (isolated, not active)

GPT-6's first real F09/F10/F14/F27 gate exposed a semantic mistake
(F09 two separate residences grouped as a single relationship) and
Core-blocking source role errors (F14/F27 date/reference/participant scopes).
A **versioned v2 prompt extension** supplements every existing v1 instruction
without changing the JSON schema, normal Router runtime, canonical NoteSchema
or Core, and is selected only with `prompt_revision="v2"` on this inactive
candidate adapter. It clarifies general product distinctions for independent
properties, mutual relationships, coherent shared encounters, explicit
sequence, lexical `date` vs `time`, exact `reference` evidence and ordinary
future activities. It does not add local keyword heuristics, rewrite spans,
guess identities, or grant write authority.

The four revised request envelopes are independently frozen in
`prompt_v2_requests.json`. The normal offline default continues to use v1
for historical reproducibility. To inspect v2 **without any provider use**:

```bash
python -m benchmarks.fact_candidate_v2_live.run_live --prompt-v2
python -m pytest -q tests/benchmarks/test_fact_candidate_v2_live_runner.py
```

The live command (only after normal approved per-call budget review) is
`python -m benchmarks.fact_candidate_v2_live.run_live --prompt-v2 --live`
inside the established transient `systemd --user` service with the fixed
EnvironmentFile, explicit authorized flag and no shell credential loading.
It makes **exactly four** calls. The revised conservative four-call reservation
is `$0.01379775`; the first observed v1 run cost is `$0.0010009`
estimated from saved token counts and pinned rates, giving a combined estimated
prior spend + *fully reserved new upper envelope* of about `$0.01480`,
below the previously approved `$0.02` total. This is not an invoice and
the final comparison must still include an independent semantic review.

## Opt-in prompt revision v3 (F10 mutual relation kind)

Revision v3 inherits the **entire v2 prompt**, adds one generic distinction
between a mutual/reciprocal relationship and an occurrence with several
participants, and leaves the JSON schema, models and Router v0 unchanged.
Its exact four synthetic requests are frozen in `prompt_v3_requests.json`.
Use `python -m benchmarks.fact_candidate_v2_live.run_live --prompt-v3` for
offline review. The conservative four-call new reservation is **USD
0.01464675**. The cumulative pre-call guard checks the previously observed
estimated standard-rate costs for both prior synthetic gates plus the full
new reservation stay below the original **USD 0.02** authorization. No
automatic retries or additional cases are possible. Even a structurally
matching result does not promote candidate semantic write authority.

In parallel, Core's *inactive opt-in* grouped/sequential source-evidence
pilots now accept alternate independently grounded exact text spans: the
two participants can be separately quoted when source offsets prove one
coherent linked clause; for two explicit contacts, literal ordered source
syntax and a same-clause date prove inheritance, while separate original
pending reference spans can form a single original-source clause. This
does not infer identity, authorize a write from Router, or activate any
normal DEV/PROD path. Isolated vertical replay tests assert that protected
Core still rejects tampered names, predicates, date scopes, order and
unverified pronouns before any Markdown write.


## Staged evaluation of the remaining 23 GPT-6 Router design cases — 2026-10-10

The four previously completed fixed cases F09/F10/F14/F27 retain their
frozen real-provider evidence. The remaining **23 IDs** (F01–F08,
F11–F13, F15–F26) are new, distinct, user-reviewed source sentences
from `benchmarks/application_router/fact_units_v2.design.json`.
These are **Router-only** calls: they establish model-generated fact
segmentation/source roles, not Core/Temporal model acceptance, safe
mutation, or general release readiness. Core stays GPT-5.6.

The new offline-default versioned `run_remaining.py` uses exactly the
unchanged GPT-6 Luna/low **Router v3 prompt and strict schema**. Every
full request is hash-pinned in `reviewed_remaining_requests.json`.
The source is a fixed synthetic sentence, with `store=false`, output
cap 4096, SDK automatic retries zero, and NO repository or vault write
except a synthetic test receipt JSON. All 23 original design oracles
must remain unchanged; source offsets, semantic count/kind/state,
roles and inherited scope require independent post-run scrutiny.
An exact fixture mismatch is a **diagnostic**, not automatic proof of
a bad interpretation; missing or wrong candidate count is a stronger
failure. Router candidates NEVER choose canonical Note types/targets.

The user previously explicitly authorized **USD 0.07 cumulative**
focused Router/Core synthetic testing. The frozen observed standard-
rate estimate already consumed **USD 0.0259652** (not an invoice).
Each additional model request reserves its full conservative worst-
case cost (~USD 0.00368 for first case) and then charges the actual
provider-reported token counts at *noncached standard rates* before
any next reservation. If the next complete conservative envelope
cannot fit USD 0.07, STOP without executing that call. The runner
fails on duplicate, out-of-order, stale hash, or previously failed
synthetic receipt, and saves **one distinct JSON per attempted call**
under `remaining_results`. It cannot retry model calls or mutate a
note. It may stop before all 23 cases if that conservative budget
constraint requires it.

Offline:
```bash
python -m benchmarks.fact_candidate_v2_live.run_remaining
python -m pytest -q tests/benchmarks/test_fact_candidate_remaining_live_runner.py
```

Live, **only within the existing authorized ordinary Pi user service**:
```bash
python -m benchmarks.fact_candidate_v2_live.run_remaining --live
```

The authorized service injects the unchanged fixed `EnvironmentFile`
and the explicit `ODYSSEY_ROUTER_V2_LIVE_APPROVED=1` flag. The
diagnostic script never reads credentials. Complete all source-only
offline contracts and publish the reviewed code BEFORE any live run.
Save the real provider output verbatim only for these 23 synthetic,
nonpersonal examples; no DEV/PROD deployment. A model result that
passes JSON validation still needs separate semantic comparison.


## Completed real GPT-6 run of the other 23 cases (2026-10-10)

**All 23 previously untested source inputs** (F01–F08,
F11–F13 and F15–F26) were each executed exactly ONCE against the real
GPT-6 Luna/low Router v3 model in the existing authorized transient Pi
user service. No provider errors, source-JSON validation errors,
retries, other models, Core calls, Notes writes or DEV/PROD activation.

Immutable 23 per-case synthetic real model replies are recorded in
`remaining_results/YYYYMMDDTHHMMSSZ--Fxx.json`, with a separate
provider-free detailed comparison at
`review_remaining_20261010.json`. Re-run the comparison with
`python -m benchmarks.fact_candidate_v2_live.analyze_remaining`.
Offline CI `tests/benchmarks/test_fact_candidate_remaining_observed_live.py`
preserves real semantic failures as failures; it does NOT fabricate an
expected model reply or replace it with fixture data.

**Observed:** 23/23 completed and structurally source-valid; **22/23
preserved the oracle number of independent units**. In seven cases
(F06, F13, F16, F19, F20, F24, F25) the kind or cardinality
differs from the original reference; **do not interpret this as seven
equivalent errors**. Other role/quote differences are also NOT yet
independently semantically accepted. Full local comparison reports 16
with only role/quote/inheritance deviations and 7 with structural
deviations, but *no automatic PASS is declared by these labels*.

### Human semantic triage by case

| Case | Original source meaning and current finding | Gate |
| --- | --- | --- |
| F01 | Three activities separated; last plural group participants not explicitly inherited | subject check |
| F02 | Three activities; approximate 16h and family participants individually preserved; 'Esta tarde' role differs | date check |
| F03 | Park walk then cinema; two events with inherited date/participants | plausible |
| F04 | Park 12:00 then cinema 18:00, same day | plausible |
| F05 | Friday Ana/Toulouse and Saturday Luis/Albi remain separate | plausible |
| F06 | Visit Ana and buy bread remain separate; bread is `purchase_item` instead of `occurrence` | compatible classification candidate |
| F07 | Bea at 15h and Luis at 17h remain separate with predicate inherited | plausible |
| F08 | Marta doctor at 10h; Luis dentist 'same hour' quoted as a time but no explicit `time_relation` source role | **temporal inheritance check** |
| F11 | Bread and milk are two purchase items with transaction/date inherited | plausible |
| F12 | Bea and children cleaning then building furniture, both events preserved | plausible |
| F13 | Yesterday Eric, tomorrow cinema with 'él', today bread preserved as three; bread classified purchase item; Core must resolve pronoun independently | pronoun/anaphora check |
| F15 | Three distinct subjects/actions including 'después' | plausible |
| F16 | Ana and Luis each buy concert tickets; both `purchase_item`, despite oracle `occurrence` | compatible classification candidate |
| F17 | Two negative claims preserved with original 'no' evidence | plausible |
| F18 | Negative Ana and positive Luis separated | plausible |
| F19 | **FAIL:** self-correction park 11h → cinema 12h emitted as TWO `occurrence` candidates, rather than ONE corrected `plan`; previous cancelled alternative risks write | **BLOCK** |
| F20 | **FAIL:** both conditional branches carry literal condition roles, but are emitted as unconditional `occurrence` rather than `conditional`; wrong downstream execution type | **BLOCK** |
| F21 | Monday and Wednesday classes 18h, correct count and shared week scope | plausible |
| F22 | Three separately dated tasks | plausible |
| F23 | Two defects (Router, Temporal) separately attached to Odyssey project; 'otro' may need source object inheritance | object binding check |
| F24 | Car at workshop then future service; `occurrence` for service instead of oracle `property` is semantically plausible | compatible classification candidate |
| F25 | **FAIL / high risk:** house needs roof repair becomes a `task` rather than an attribute/requirement; must not silently create a task assigned to user | **BLOCK** |
| F26 | Report arrival and later sending separated; 'lo' explicitly marked reference but lacks direct inherited object binding to 'El informe' | **coreference check** |

**Risk assessment:** F19 and F20 are clear real Router semantics blockers,
F25 is a task-vs-property side-effect blocker. F08/F13/F23/F26 and
possibly F01/F02 need independent Core/Temporal provenance review,
not automatic approval. The remaining fixture differences may be
valid equivalent interpretations; do not change acceptable behavior
just to satisfy an exact literal quote oracle.

**Cost:** Real GPT-6 Router 23-call model usage totals about
**USD 0.0077700**, estimated using pinned *standard noncached* prices.
Combined estimated prior focused GPT-6 Router and GPT-5.6 Core
testing, the cumulative focused estimate is **USD 0.0337352**,
beneath the explicitly authorized **USD 0.07** (not a provider invoice).
The historical F09/F10/F14/F27 model results are unchanged, and
Core remains on GPT-5.6.

**Next scoped work:** Improve the *generic* source kind contract and
closed prompt for correction/conditional/implicit repair tasks,
introducing source-only negative/conditional semantic sentinels;
then independently verify temporal inheritance and references before
adding per-unit Core planning for these more diverse shapes.
Do NOT turn Router into a task/note writer or bypass Core identity
and semantic coverage. No current production runtime changes.
