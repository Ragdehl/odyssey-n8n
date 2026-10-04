# Fixed-fact semantic enrichment live gate v2

This is the focused successor to v1 after v1 showed that Luna could leave a bounded SELF relation entirely literal when it appeared alone. The production change is abstract: wording that itself defines a bounded identity universe through SELF or one bounded source must be exposed as an identity with `candidate_scope`; Core still owns all resolution and falls back to literal if grounding fails.

The three v1 cases are retained unchanged: nickname-like identity, complete SELF set, and the mixed real-world shape containing both. No Calendar-specific alias, child, dinner, or source-type rule is added.

- Model: GPT-5.6 Luna, reasoning `low`.
- Maximum 3 calls, zero retries, zero Sol calls, no vault mutation.
- Provider authority remains zero until the exact contract, cases, budget, clean worktree, and explicit authorization flag all match.
