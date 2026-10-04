# Core Temporal semantic-write focused live gate v2

This one-shot gate closes the remaining production-model evidence gap left by `router_temporal_core_live_v1` after its Core model-facing contract was narrowed.

## Why this gate exists

The consumed v1 gate found that GPT-5.6 Luna emitted `complete_set` candidate scope inside a fact identity part for `Bea y mis hijos`. The deterministic compiler already rejected that shape because a fact reference must denote one identity. The provider schema and planner instructions were then aligned generically: fact identity parts permit only `one_member`, while a genuine operation target may still use `complete_set`.

That is a material model-facing schema/instruction change, so provider-free tests alone are not final readiness evidence.

The old compound Ana/Luis Core failure is intentionally **not** repeated here: Router v6 now splits independently interpretable clauses before Core, and its successor live gate passed that behavior 17/17.

## Frozen scope

Four GPT-5.6 Luna / low calls, zero retries and zero mutation authority:

1. `Hoy hemos vaciado el garaje con Bea y mis hijos.` — direct regression for set-valued participant wording.
2. `Mañana a las 15:35 voy al parque con Bea y mis hijos.` — same regression with exact date-time evidence.
3. `Hoy cené con Bea y mi hijo al que le gusta el fútbol.` — singular qualified relationship sentinel.
4. `Mañana a las 15:35 voy a ver a mi amigo del barrio que tiene un barco.` — singular descriptive relationship sentinel.

Frozen matrix SHA-256: `3600ad45d021b29e1819274118c9cbfa29d54ee1b82ad85900deaca1a5643e92`.

## Cost and safety envelope

- maximum provider attempts: **4**
- automatic retries: **0**
- mutation authority: **false**
- conservative input envelope: 40,000 tokens/call
- production output limit: 2,048 tokens/call
- conservative regional upper bound: below **$0.05**
- hard runner ceiling: **$0.05**

`python -m benchmarks.core_temporal_write_live_v2.run_live --preflight` performs only local validation and makes zero provider calls.

A real run is refused unless `ODYSSEY_RUN_CORE_TEMPORAL_WRITE_V2=1` and `OPENAI_API_KEY` are present, `git diff --check` passes, the frozen matrix digest still matches, and no v2 result already exists. Explicit human authorization is still required before setting the technical gate flag.

## Consumed result

The authorized v2 run completed all four GPT-5.6 Luna / low calls with zero retries and zero mutation authority. Result: **4/4 passed**. Estimated regional cost was `$0.01135904`; immutable evidence is retained in `results/f6d14c572ab5.json`.

This closes the `complete_set` fact-reference mismatch itself. A later disposable full-runtime E2E exposed a separate Calendar Day provider-schema mismatch for `Mañana a las 15:35 viene el fontanero.`: Luna parsed successfully but failed local semantic-write compilation, and the bounded Sol fallback then failed Calendar Day target validation. No canonical mutation occurred. That later issue is not evidence against this consumed four-case gate; it belongs to a fresh successor contract and must not cause v2 to be overwritten or retried.
