# Authorized Router/Core follow-up v3-8

This retained one-shot artifact records the exact live scope explicitly authorized by the user on 2026-10-04: **5 Router GPT-6 Luna / medium calls + 3 Core GPT-5.6 Luna / low calls**, maximum 8 provider calls, zero retries, zero mutation authority, and a hard cost ceiling of `$0.05`.

It intentionally excludes the later-added direct Sol sentinel in `router_core_followup_live_v3`; that ninth call and its `$0.31` envelope were never authorized and were not executed.

## Consumed result

- provider attempts: **8/8**
- automatic retries: **0**
- mutation authority: **false**
- estimated regional cost: **$0.00932448**
- overall: **6/8 passed**
- Core: **3/3 passed**, including `Mañana a las 15:35 viene el fontanero.`
- Router: **3/5 passed**

Router failures were bounded to the dependent no-split sentinels:

1. `Hoy vi a Ana y compré pan.` was incorrectly split, losing shared temporal scope from the second route.
2. `Hoy a las 15:00 veo a Bea y a las 17:00 a Luis.` returned `NEEDS_CAPABILITY` instead of one Temporal route.

No retry was performed. The immutable consumed evidence is `results/1ede7c7f9b92.json`.

After this evidence, the Router prompt was corrected generically around truth-condition completeness of exact spans and capability choice by requested lifecycle semantics rather than surface resemblance. Provider-free regressions and disposable user-path E2E are green; that later prompt revision has **not** received another live model call under this authorization.
