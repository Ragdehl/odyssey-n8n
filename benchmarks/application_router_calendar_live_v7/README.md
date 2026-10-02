# Calendar-focused live gate v7

Attempt 6 was prepared with Calendar GPT-6 Luna `medium` after Attempt 5 showed one low-effort regression, but it was retired **without any provider call** after prompt review found a real semantic ambiguity: a transition can simultaneously be a Day occurrence and the start/end/change of durable entity-owned knowledge.

The v7 candidate returns Calendar to GPT-6 Luna `low` and changes only the generic Calendar planner contract: when both readings apply, durable entity-owned knowledge takes precedence over `DAY_LITERAL_CAPTURE`. The prompt contains no case-specific names or examples. `DAY_LITERAL_CAPTURE` remains reserved for occurrences whose semantic content belongs to the Day and does not establish, end, or change durable knowledge about a reusable identity.

Router is not re-called in this gate. Attempt 5 already passed Router 8/8, and v7 preflight refuses to run if `odyssey_apps/router.py` or the production Calendar descriptor differ from the exact Attempt-5 pass commit. Calendar regression v3 retains all 8 v2 cases and adds two distinct transition sentinels (ending employment and starting residence) so a pass cannot rely only on the original Marta/Airbus wording.

The gate is one-shot, zero-retry, requires a clean exact commit, frozen matrix hash, credential presence, explicit authorization flag, and an empty result directory. Its 10-call conservative ceiling is $0.01084560 Standard / $0.01193016 with regional uplift; hard stop $0.012. No v7 provider call has been made.
