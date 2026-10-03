# Application Router + Calendar live gate v10

> **Historical evidence only — Core oracle partially invalid.** The employment cases treated `Airbus Test` as an Odyssey identity even though the canonical `note-schema` has no company/organization type. Calendar branch evidence remains useful, but the Core start/end identity expectations must not be used as acceptance evidence.

v10 replaces the unexecuted v9 gate after the application/Core boundary was simplified. Applications now emit only bounded domain interpretation; they never construct Core semantic-write targets, identities, facts, candidate scopes, or RequestPlans. Calendar therefore returns either a Day-owned literal capture, a fail-closed temporal result, or `DELEGATE_TO_CORE` with only exact temporal evidence. Core then performs the ordinary semantic planning.

Router is not re-run: its retained v5 evidence already passed 8/8 and the Router model-facing boundary is pinned unchanged by preflight. The Calendar matrix contains eight non-redundant branch sentinels. The Core handoff matrix contains only the two exact DEV regressions that exposed the former mini-planner boundary (`Marta Test` / `Bruno Test` with `Airbus Test`).

The gate performs at most 10 provider attempts with zero automatic retries: eight GPT-6 Luna `low` Calendar calls and two production GPT-5.6 Luna `low` Core calls. The conservative no-cache byte-as-token regional upper bound is $0.03347806 and the hard authorization ceiling is $0.034. The runner has no mutation authority and writes only a retained synthetic evidence artifact. No live call is allowed without a clean exact commit, unchanged frozen matrices, credential presence through the approved one-shot environment, and explicit `ODYSSEY_RUN_APPLICATION_ROUTER_CALENDAR_V10=1`.
## Retained result

v10 ran once on `ed5ddf43761169dfdca8c37c1575e22a081a1aa5`. All 10 provider attempts completed with zero retries. Calendar passed 8/8 and the Core handoff start-transition case passed. The Core handoff end-transition case failed because Core preserved `Airbus Test` as literal text instead of an identity reference. Actual estimated cost was $0.00601230 Standard / $0.00661353 regional. No rerun is permitted under v10.

