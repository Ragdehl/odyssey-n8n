# Complete-set fact participant live gate v1

This one-shot gate closes the model-facing correction for relationship-bounded complete sets used as participants inside ordinary facts. The model may describe set semantics but never supplies concrete member identities; Core re-grounds and expands every member immediately before persistence.

Frozen scope:

- 3 direct GPT-5.6 Luna / low calls: date-only complete set, exact-time complete set, and qualified singular-member regression.
- 1 direct GPT-5.6 Sol / low call: date-only complete set through the production fallback contract.
- zero automatic retries and zero mutation authority.
- maximum 4 provider calls.
- frozen matrix SHA-256 `a77c68f4748001d3b93df01f90d906692593dc1ba083b85bd77051cc6adb3e41`.

The conservative regional budget envelope is bounded below `$0.31`, dominated by the single production-config Sol call. `--preflight` makes zero provider calls. A live run requires explicit human cost authorization, `ODYSSEY_RUN_COMPLETE_SET_FACT_V1=1`, and the protected provider environment.

## Recorded result

The consumed v1 evidence made four provider calls with zero retries and zero mutation authority. Luna passed all three semantic cases, including `complete_set` with date/time and the qualified singular regression. The legacy Sol fallback understood `mis hijos` as `complete_set` but produced invalid provider-owned `{{ref:N}}` numbering, so Core failed closed. This result is retained as historical evidence that the semantic interpretation was correct while the legacy Sol wire contract was mechanically divergent.
