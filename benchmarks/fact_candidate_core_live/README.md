# Two-case GPT-5.6 Core planning gate — prepared, not authorized or run

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
