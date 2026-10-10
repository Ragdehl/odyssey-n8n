# Two-case GPT-5.6 Core planning gate — executed once after approval

The current experimental Router v3 has passed **four** synthetic GPT-6 source
semantics checks. This is a **separate** diagnostic for the Core planner's own
meaning and canonical write plans for **F09 and F10 only**. The prior Router
spending approval of USD 0.02 does **not** independently authorize increasing
the total budget here.

## Scope

- **F09:** Marta and Luis independently live in Lyon. Core should choose
  independent person-targeted facts without conflating two people.
- **F10:** Marta and Luis mutually met in Lyon. Core should represent a
  **single** relationship, without inventing a date or duplicating it under
  two independently claimed relationship facts.
- Model remains **GPT-5.6 Luna / low**, exactly its current experimental
  production-shaped request prompt and strict schema, 2048 max output tokens.
- Input is two fixed synthetic sentences plus previously captured source-only
  GPT-6 Router v3 facts; **no personal Notes or vault**, **no provider access
  during preparation**, no note-writing authority, no Core/Router rollout.
- Exact canonical source-bearing provider request SHA-256 hashes and sizes
  are pinned in `reviewed_requests.json`. Each live call has `store=false`
  and is issued via a fresh no-retries OpenAI client, with no automatic
  provider retry. Each response is preserved for independent manual review.
- The prompt includes the canonical NoteSchema but **not actual identities
  in the user vault**. A `PLAN`, `CLARIFY` or `ESCALATE` is only an
  observation, not permission to persist it.

## Offline-only checks (safe, already available)

```bash
cd /home/ragdehl/projects/odyssey-fact-candidates-v1
/home/ragdehl/projects/odyssey-dev/.venv/bin/python -m benchmarks.fact_candidate_core_live.run_live
/home/ragdehl/projects/odyssey-dev/.venv/bin/python -m pytest -q \
    tests/benchmarks/test_fact_candidate_core_live_runner.py \
    tests/runtime/test_fact_candidate_person_property_vertical.py
```

## Separate explicit approval required before live

The very conservative full two-call reservation is **USD 0.06344020**.
The earlier three Router tests consumed approximately **USD 0.00323560**
under the project's pinned standard rates; combined prior estimated spend
and worst-case new reservation is **USD 0.0666758**, requiring a separately
approved **USD 0.07 cumulative cap**. These are not billed/invoice amounts.
Do **not** silently reuse the earlier USD 0.02 Router authorization. **No
live Core provider execution has occurred in this checkpoint.**

Once the operator **explicitly** approves this new cumulative ceiling, the
reviewed command can be run in the existing Pi transient `systemd --user`
unit with the fixed
`EnvironmentFile=/home/ragdehl/.config/odyssey/secrets.env`, an explicit
`ODYSSEY_CORE_FACT_LIVE_APPROVED=1`, and
`python -m benchmarks.fact_candidate_core_live.run_live --live`.
The script does not load or print secrets and is not a replacement for
real application deployment. If tool execution is rejected, stop and report
the exact refusal rather than bypassing it.

An observed successful JSON/schema validation is *not* independent semantic
verification. The operator must review exactly what person notes, references
and counts the provider proposes, check it against frozen F09/F10 meaning,
and validate any proposed write plan with independent Core coverage and
disposable Markdown tests. The other 23 Router cases and normal DEV/PROD
activation remain out of scope.

## Executed focused gate — 2026-10-10 (after separate approval)

The operator **explicitly approved the USD 0.07 cumulative cap**. The
reviewed, pinned F09/F10 gate then executed once in the authorized transient
Pi user service. Both real GPT-5.6 Luna/low responses completed and passed
the unchanged production-shaped Core semantic planner schema:

- **F09**: one real Core `WriteAction` with **two** Person writes,
  `target=Marta, fact="Vive en Lyon."` and
  `target=Luis, fact="Vive en Lyon."`.
- **F10**: one real Core `WriteAction` with **one** fact
  `Se conoció con {{ref:0}} en Lyon.` on Marta, plus a
  lookup-only `Luis` helper. This is a single reciprocal relationship
  (not two independent events). The Spanish wording is awkward and will
  need a later language-quality assessment.

Raw **synthetic-only** Responses JSON, local validation, compiled plan and
usage are frozen in `results/20261010T200525Z.json`. Observed:
**21,004 input / 651 output tokens**. At pinned standard rates, estimated
new Core cost **USD 0.004982**; with previous focused Router calls,
estimated cumulative **USD 0.0082176** (not invoice).

The first offline replay of these exact real plans revealed two separate
narrow Core coverage false negatives: implicit person subjects in the
original Note-targeted F09 facts, and F10's single canonical fact with one
other-person helper rather than F14's unrelated two-person group event.
Core now owns separate, conservative provenance guards:
`candidate_property_evidence.py` verifies source subject ↔ exact Core
typed target, non-subject location/object content and absence of a
different candidate's subject in the fact; `candidate_mutual_relation.py`
verifies one explicit original reciprocal clause, both named participants,
one Person target, exactly one non-mutating other-person helper, consistent
predicate and location, and no added dates. They retain the existing
negative/denial checks; the Router has **no write authority**.

Offline replay of the **real saved provider-generated plans** through Core
on isolated Markdown vaults now physically proves:
- F09 two correct independent existing Person facts, as well as creating
  **two new canonical Person Notes** from the same approved singular
  identity selection lifecycle when both people are absent and conflict-free
- F10 one factual Markdown entry on Marta, a genuine Luis wikilink, and
  the backlinks that make the single fact visible from Luis
- negative source/target swaps, wrong cities/predicate, extra negation,
  unsupported date, duplicate relationship and mutating helper all rejected
  before writing

These are narrowly proven **four focus cases** under seeded/resolvable
test conditions, **not a new production runtime**, a global relationship
ontology, the other 23 source cases, or an end-to-end real chat path. No
new live Core calls or personal vault writes are planned here.
