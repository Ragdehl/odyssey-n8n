# Application Router + Calendar Planner live gate v3

Attempt 3 keeps the accepted Router-v1 and Calendar-v2 oracles unchanged. It follows the reviewed Attempt-2 evidence: Router already passed 8/8, while Calendar's two remaining failures showed that its Core-write Structured Output still exposed more generic Core authority than this application needs.

The candidate is structural rather than case-specific. Calendar checks its own semantic scope before temporal normalization. Its model-facing Core-write branch exposes only one-or-more fact-only `record` operations over generic identities: note types, filters, properties, tags, destination types, reclassification, and bulk selection are unavailable. The local decoder enforces the same authority after parsing, so bypassing the provider schema still cannot reach Core with those fields.

The runner executed once at `3319f6d4d1ec389140b7c722e70ab9670ce948dd`. Router completed all eight cases, with six exact oracle passes, one harmless whitespace-allocation mismatch in the independent split, and one material dependent-route regression back to Core. Calendar produced no completed provider responses: all eight attempts failed at the provider/schema boundary with `CalendarPlannerError`, so no Calendar semantic result can be inferred from this attempt. The retained artifact records eight completed provider responses, zero retries, and $0.00071090 Standard / $0.00078199 regional-upper usage cost. No retry or continuation was made.

Provider-free budget for the complete 8 Router + 8 Calendar matrix is 16 calls. The conservative no-cache ceiling is $0.01242540 Standard / $0.01366794 with the 10% regional uplift.
