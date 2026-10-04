# Complete-set fact participant live gate v2

Successor to v1. V1 proved the current semantic WRITE contract on Luna (3/3), while the historical low-level Sol planner independently understood `complete_set` but failed on model-authored `{{ref:N}}` numbering. Production no longer uses that second WRITE language.

V2 makes exactly one GPT-5.6 Sol / low call through the **same semantic frontend** used by Luna: same prompt, structured-output schema, `SemanticWriteIntent` compiler, local validation, 2048 output-token cap, zero SDK retries, and no mutation authority. The only intentional provider-boundary difference is `model=gpt-5.6-sol`.

- one call maximum;
- zero retries;
- zero mutation authority;
- matrix SHA-256 `9d35be2fb16e060d99b38a61f717ac0c52b3f06269a4cb8cf4f263939f64b915`;
- conservative regional ceiling `< $0.23` using a 40k-token input envelope and the dated Sol rate assumptions already used by v1.

`--preflight` performs no provider calls. Live execution requires fresh explicit authorization plus `ODYSSEY_RUN_COMPLETE_SET_FACT_V2=1`.

## Recorded result

The consumed v2 successor made exactly one GPT-5.6 Sol / low call through the same semantic frontend used by Luna. It passed: `mis hijos` was emitted as a `complete_set` identity part, Core deterministically lowered references to `{{ref:0}}` / `{{ref:1}}`, and the date anchor remained `2026-10-04`. Estimated regional cost was `$0.0531916`; automatic retries and mutation authority were both zero.
