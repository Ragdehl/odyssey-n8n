# Calendar-focused live gate v8

Attempt 7 ran Calendar GPT-6 Luna `low` on 10 cases after the durable-transition precedence clarification. All 10 provider calls completed with zero retries. Eight cases passed. Both employment transition sentinels chose `CORE_SEMANTIC_WRITE`; the residence transition also chose `CORE_SEMANTIC_WRITE`, so the precedence rule itself held. Two orthogonal issues remained: a correct `FAIL_CLOSED/TEMPORAL_UNRESOLVED` response carried a stale non-executable intent allowed by the flat provider schema and rejected locally, while the added Lyon case coupled transition classification to the separate question of whether a place must be emitted as an Odyssey identity.

v8 keeps Calendar on GPT-6 Luna `low` and does not change the precedence prompt or provider schema. The local decoder now normalizes an irrelevant intent to `None` only when `outcome=FAIL_CLOSED`, there is no semantic write, and a concrete failure code is present; all temporal/failure correlation checks remain mandatory and no execution authority is created. Calendar regression v4 preserves every consumed v3 case except the newly added residence sentinel, which now uses a second person (`Daniel`) as the clearly reusable identity participant instead of requiring a place (`Lyon`) to be classified as an identity.

Router is not re-called: its retained Attempt-5 8/8 boundary is still required to be unchanged. The gate remains one-shot, Calendar-only, zero-retry, clean-commit-only, explicitly authorized, and capped at 10 provider attempts.

Provider-free budget for the 10-case gate is $0.01084590 Standard / $0.01193049 with regional uplift; hard stop remains $0.012. No v8 provider call has been made.
