# Application Router + Calendar Planner live gate v2

This successor gate keeps both Attempt-1 matrices byte-identical and changes only the candidate model-facing instructions after reviewing all five Attempt-1 failures as real candidate-contract/model failures.

The revision is general rather than case-specific:

- Router chooses the capability required to interpret one dependent intent, independently from the canonical knowledge owner that may later receive a Core write.
- Calendar resolves temporal shape before classifying semantics; future/datetime wording alone does not make an occurrence a Task.
- Calendar reuses the shared semantic-write distinction between safely selectable logical participants and literal context/values.

The runner retains each synthetic Structured Output before local parsing so a fail-closed correlation error remains diagnosable without another provider call. It refuses execution unless both frozen matrix hashes match, the worktree is clean, no v2 result exists, `OPENAI_API_KEY` is present, and the explicit `ODYSSEY_RUN_APPLICATION_ROUTER_CALENDAR_V2=1` authorization flag is set.

Provider-free budget calculation for the complete 8 Router + 8 Calendar matrix is 16 calls, at most 107,326 input bytes under the deliberately conservative one-byte-per-token bound and 12,288 configured maximum output tokens. At current GPT-6 Luna Standard rates this is $0.01687660; including a 10% regional uplift gives a $0.01856426 ceiling. No v2 provider call has been made yet.
