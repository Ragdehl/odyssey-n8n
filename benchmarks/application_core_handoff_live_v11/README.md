# Application → Core handoff live gate v11

v10 proved the redesigned boundary: Router retained 8/8, Calendar passed 8/8, and the Core start-transition handoff passed. Its only failure was the end-transition case, where GPT-5.6 Luna low kept `Airbus Test` as literal text instead of an identity participant.

v11 changes only the existing generic Core identity-decomposition instruction. Participant decomposition must remain stable when a durable relationship or state begins, continues, ends, is negated, or is corrected. No concrete person, employer, or Calendar-specific semantic rule is added.

The gate is Core-only. It reuses retained Router v5 8/8 and Calendar v10 8/8 evidence, then makes exactly two GPT-5.6 Luna low calls: the DEV employment-ending reproduction and a distinct person-to-person ending relation. Both receive only generic `DomainInterpretation` temporal evidence; Core must independently select the target, identity participant, fact, and Day reference.

The runner is one-shot, zero-retry, mutation-free, requires a clean worktree and explicit `ODYSSEY_RUN_APPLICATION_CORE_HANDOFF_V11=1`, and refuses a second result. The conservative byte-as-token regional ceiling is below $0.030.
## Retained result

v11 ran once on `641939fb3effc07c29694998263edf3900ad99ae`. Both GPT-5.6 Luna low provider attempts completed with zero retries and both cases passed: the retained DEV employment-ending reproduction kept `Airbus Test` as an identity reference, and the distinct person-to-person ending relation kept `Daniel Test` as an identity reference. Estimated actual cost was $0.00490840 Standard / $0.00539924 regional. No rerun is permitted under v11.
