# Application Router + Calendar Planner live gate v6

Attempt 6 is the provider-free stability successor to retained Attempt 5. Router already passed 8/8 after the production Calendar descriptor correction. Calendar passed 7/8; only the entity-owned exact-date case regressed from `CORE_SEMANTIC_WRITE` to `DAY_LITERAL_CAPTURE` even though the identical Calendar prompt/schema had passed that case in Attempt 4.

The v6 candidate therefore changes exactly one production model-facing setting: Calendar GPT-6 Luna reasoning effort moves from `low` to `medium`. Router remains GPT-6 Luna `medium`. Calendar prompt, app-native schema, local decoder, production descriptor, Router prompt/schema, matrices, and semantic oracles are unchanged.

The one-shot runner reuses Router v2 and Calendar v2, imports the production Calendar descriptor, counts provider attempts separately from completed responses, uses zero automatic retries, and retains only synthetic output/usage plus sanitized provider-failure metadata. It requires unchanged matrix hashes, a clean exact commit, an empty v6 result directory, credential presence, and an explicit v6 authorization flag. No v6 provider call has been made.

Provider-free budget for the complete 8 Router + 8 Calendar matrix is 16 attempts: $0.01212620 Standard / $0.01333882 with the 10% regional uplift. The hard ceiling remains $0.014.
