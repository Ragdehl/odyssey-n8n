# Application Router + Calendar Planner live gate v2

This successor gate keeps the Attempt-1 Router matrix byte-identical and uses a versioned Calendar v2 oracle after reviewing all five Attempt-1 failures as real candidate-contract/model failures.

The revision is general rather than case-specific:

- Router chooses the capability required to interpret one dependent intent, independently from the canonical knowledge owner that may later receive a Core write.
- Calendar knows only Calendar semantics; foreign-domain input is generic `OUT_OF_SCOPE`, while Router alone knows sibling applications.
- Calendar reuses the shared semantic-write distinction between safely selectable logical participants and literal context/values.

The runner retains each synthetic Structured Output before local parsing so a fail-closed correlation error remains diagnosable without another provider call. It refuses execution unless the frozen Router-v1 and Calendar-v2 matrix hashes match, the worktree is clean, no v2 result exists, `OPENAI_API_KEY` is present, and the explicit `ODYSSEY_RUN_APPLICATION_ROUTER_CALENDAR_V2=1` authorization flag is set.

Attempt 2 ran once at commit `459956a57770fd4e55c3dab75fa9cd7c58320e2b` after explicit authorization. It used exactly 16 GPT-6 Luna/low calls, zero automatic retries, 19,680 input tokens and 2,643 output tokens. Estimated cost was $0.00328950 Standard / $0.00361845 with the regional uplift. Router passed 8/8. Calendar passed 6/8 and the overall gate failed. The two retained failures were both foreign-domain defense cases: an obligation was rejected as `TEMPORAL_UNRESOLVED` instead of generic `OUT_OF_SCOPE`, and an explicit diary write was incorrectly represented as `CORE_SEMANTIC_WRITE`. No retry or follow-up provider call was made. The result is retained under `results/459956a57770.json` and this v2 runner is consumed evidence, not authority for another run.
