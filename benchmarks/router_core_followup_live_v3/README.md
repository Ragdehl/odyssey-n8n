# Router/Core disposable-E2E follow-up live gate v3

This one-shot gate validates only the two model-facing boundaries changed after disposable full-runtime E2E evidence.

## Triggering evidence

A disposable user-path request `Ayer vi a Ana y hoy vi a Luis.` completed correctly but Router produced one Temporal route instead of the approved two independently interpretable routes. The Router prompt therefore gained one generic irreducibility self-check; no phrase-specific or language-specific rule was added.

A second disposable request, `Mañana a las 15:35 viene el fontanero.`, failed closed before mutation. Luna parsed but failed local semantic-write compilation; bounded Sol fallback then failed Calendar Day selection. Review found provider schemas still admitted Calendar Day shapes that deterministic Core rejects. The candidate now correlates Luna Calendar Day targets with `one + record + facts-only` and restricts the Sol Calendar Day target branch to trusted exact dates with no ordinary selection mechanisms. Core validation rules are unchanged.

## Frozen scope

- 5 Router GPT-6 Luna / medium calls: three independent split repetitions plus two dependent no-split sentinels.
- 3 Core GPT-5.6 Luna / low calls: Day exact date-time, `Bea y mis hijos` date regression, and ordinary entity exact date-time.
- 1 direct GPT-5.6 Sol / low call for the same Day exact-date-time case that failed in the bounded production fallback. This is required because the fix also changes Sol's production Structured Output target branch.
- maximum **9 provider calls**; zero automatic retries; zero mutation authority.
- frozen matrix SHA-256: `17ce0ed065d8eaae861668977b644b43ba0a101fa9b771ca88d3bd1bc0595194`.

The deliberately conservative regional envelope is `$0.30753008`, dominated by the one Sol call's 40,000-input-token and 4,096-output-token production envelopes. The runner hard-stops above **$0.31** and refuses any second v3 result. Actual cost is expected to be lower but is not used to weaken authorization. `--preflight` makes zero provider calls. A live run still requires explicit human authorization plus `ODYSSEY_RUN_ROUTER_CORE_FOLLOWUP_V3=1` and the protected provider environment.
