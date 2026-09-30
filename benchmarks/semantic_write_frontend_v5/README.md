# Semantic WRITE frontend v5

This gate is permanently consumed. The user authorized the 13-case Luna/low gate at its `$0.1664832` conservative ceiling. It passed SWR01-SWR07 and stopped fail-fast on SWR08 after eight completed Luna/low calls, with zero retries and zero Sol calls.

SWR08 preserved the full daughter target and the described companion, but the companion lost its required bounded event-source scope. The run also exposed an older oracle detail that was too strict: it required `relational_reference.reference` to contain `mayor`, while the deterministic semantic compiler intentionally uses the broader `mi hija` candidate anchor and keeps `mayor` in the full target query. That oracle detail is corrected for the successor; the real bounded-companion failure remains.

Artifact SHA-256: `a94c33198b96bfbb152e3402ba04e7acba6fbeafff8e4b315fb9343c07d9987c`. Usage-backed cost: `$0.00604402`. The v5 runner is permanently locked at `$0.00`.
