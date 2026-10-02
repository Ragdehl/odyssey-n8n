# Application Router + Calendar Planner live gate v5

Attempt 5 is a provider-free successor to retained Attempt 4. Calendar already passed 8/8 in Attempt 4; the sole remaining failure was Router sending the dependent temporal statement `Marta empieza mañana a trabajar en Airbus.` to Core even with GPT-6 Luna `medium`.

The v5 candidate changes only capability evidence: the production `CALENDAR_DESCRIPTOR` now states that Calendar owns temporal interpretation of date-qualified statements in addition to day/date-owned occurrences and Calendar navigation. Router prompt, Router reasoning (`medium`), Calendar prompt, Calendar reasoning (`low`), schemas, and frozen semantic oracles remain unchanged. The v5 runner imports the production descriptor directly so benchmark and runtime catalog evidence cannot drift.

The runner remains one-shot, counts provider attempts separately from completed responses, uses zero automatic retries, retains only synthetic outputs/usage plus sanitized provider-failure metadata, and requires exact matrix hashes, a clean commit, an empty v5 results directory, credential presence, and explicit v5 authorization. Provider-free budget for the complete 8 Router + 8 Calendar matrix is 16 attempts: $0.01212620 Standard / $0.01333882 with the 10% regional uplift. The hard ceiling remains $0.014. No v5 provider call has been made.
