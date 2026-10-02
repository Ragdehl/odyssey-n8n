# Application Router + Calendar Planner live gate v5

Attempt 5 is a provider-free successor to retained Attempt 4. Calendar already passed 8/8 in Attempt 4; the sole remaining failure was Router sending the dependent temporal statement `Marta empieza mañana a trabajar en Airbus.` to Core even with GPT-6 Luna `medium`.

The v5 candidate changes only capability evidence: the production `CALENDAR_DESCRIPTOR` now states that Calendar owns temporal interpretation of date-qualified statements in addition to day/date-owned occurrences and Calendar navigation. Router prompt, Router reasoning (`medium`), Calendar prompt, Calendar reasoning (`low`), schemas, and frozen semantic oracles remain unchanged. The v5 runner imports the production descriptor directly so benchmark and runtime catalog evidence cannot drift.

Attempt 5 ran once at commit `e186cf48561cfda9097f42268c8efaa82bab18bf`: all 16 provider attempts completed with zero retries for $0.00223250 Standard / $0.00245575 with the regional uplift. Router passed 8/8, confirming the production descriptor correction. Calendar passed 7/8; only the entity-owned exact-date statement regressed from `CORE_SEMANTIC_WRITE` to `DAY_LITERAL_CAPTURE`, despite the unchanged Calendar prompt/schema having passed that case in Attempt 4. The gate therefore failed overall. The evidence is retained below and must not be rewritten.

The next candidate should test Calendar GPT-6 Luna at `medium` reasoning without changing its prompt, schema, or frozen oracle, because the remaining failure is now repeated-output instability under the same Calendar contract rather than a missing semantic rule.
