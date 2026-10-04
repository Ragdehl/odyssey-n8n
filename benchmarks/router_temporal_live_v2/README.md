# Router v6 + Temporal v1 focused live gate

This is the one-shot successor to `router_temporal_core_live_v1` after the Router splitting contract changed from "different capability owners" to "independently interpretable material intentions".

## Frozen scope

- Router: full `application_router/regression_v6.json` — 17 calls, GPT-6 Luna / medium.
- Temporal: full `temporal_interpreter/regression_v1.json` — 6 calls, GPT-6 Luna / low.
- Core planner: **not called**. The current change is Router-facing; Core/Temporal deterministic contracts are already covered provider-free.
- Maximum: **23 provider calls**, zero automatic retries, zero mutation authority.
- Frozen matrix SHA-256: `e6ea6722307f11af1d034b6156545771d7ff54abea9f272e7e6f87cb8110ac69`.

The Router oracle includes the new same-capability split sentinels:

- `Ayer vi a Ana y hoy vi a Luis.` -> two ordered Temporal routes.
- `Marta vive en Lyon. Luis vive en París.` -> two ordered Core routes.

It also freezes the corresponding no-split boundaries for shared temporal scope, shared predicates, ellipsis, and one shared event with several participants.

## Cost envelope

The runner uses the production 512-token output limits, a deliberately conservative 10,000-input-token envelope per call, current gate pricing constants, and the 10% regional multiplier.

- conservative upper bound: `$0.03177680`
- proposed hard ceiling in the runner: `$0.04`

The previous v1 Router/Temporal provider calls were far below this conservative envelope, but historical usage is not used to weaken the hard ceiling.

## Safety / execution

`python -m benchmarks.router_temporal_live_v2.run_live --preflight` performs only local validation and makes **zero provider calls**.

A real run is refused unless all of the following are true:

1. the frozen matrix and source matrices still match their pinned SHA-256 digests;
2. `git diff --check` passes;
3. `ODYSSEY_RUN_ROUTER_TEMPORAL_V2=1` is present;
4. `OPENAI_API_KEY` is present;
5. the `results/` directory contains no previous v2 JSON artifact.

Setting the environment flag is only a technical guard. The gate must still receive fresh explicit human authorization before any live run. A consumed v2 result must never be overwritten or retried under the same version.

## Consumed v2 live result

The authorized one-shot run consumed exactly **23 provider attempts**, with zero retries and no mutation authority. Estimated regional cost was **$0.00318230**. Overall result: **22/23 passed**.

- Router v6: **17/17**. Both new same-capability splits and all four no-split boundaries matched the frozen oracle.
- Temporal v1: **5/6**.
- The only failure was `exact-datetime`. Luna correctly returned the exact source span, `EXACT_DATETIME`, and local wall time `2026-10-05T15:00:00`, but omitted the canonical UTC offset. Local validation rejected the response; no downstream Core execution or mutation occurred.

The retained artifact is `results/e1beaa4e406b.json`. It is immutable historical evidence and v2 must not be rerun.

## Provider-free successor correction

Review showed that the failed value contained all semantic information the model should own: the resolved local calendar date and clock time. The missing UTC offset is deterministic from the already supplied runtime IANA timezone and should not depend on model compliance.

The provider-decoding boundary now accepts an unambiguous local ISO wall time and resolves its offset deterministically from the runtime timezone before constructing the canonical `TemporalResolution`. Canonical Core values remain offset-aware and `normalize_iso_datetime()` remains strict. Ambiguous DST folds and nonexistent local wall times still fail closed instead of being guessed.
