# Application Router + Calendar live gate v9

This is the unexecuted successor to retained v8 evidence. v8 exposed a real oracle gap: the entity-owned case passed because it checked only identity mentions, while the raw provider output selected `Marta` from a `Marta` candidate scope and `Airbus` from an `Airbus` candidate scope. That shape is not executable as an ordinary named identity in Core.

v9 keeps the existing Router v2 matrix and introduces Calendar regression v5. The Calendar matrix preserves all v4 cases, strengthens the three entity-transition cases with `direct_name` selection expectations plus a real `compile_semantic_write` check, and adds the two exact DEV failures observed on 2026-10-02: `Marta Test empieza mañana a trabajar en Airbus Test.` and `Bruno Test deja mañana de trabajar en Airbus Test.`.

The production Calendar prompt now states the same generic identity rule already used by Core: explicit proper name/alias wording uses `direct_name`; `candidate_scope` is only for membership or relationship to SELF or another distinct source. The local decoder also rejects a candidate scope whose source is the selected identity itself. No case-specific names are added to the production prompt.

The gate is one-shot, zero retry, and requires a clean exact commit, `OPENAI_API_KEY`, and explicit `ODYSSEY_RUN_APPLICATION_ROUTER_CALENDAR_V9=1`. It performs 8 Router calls and 12 Calendar calls, for at most 20 provider attempts. The conservative byte-as-token regional upper bound is below $0.020; actual usage is expected to be much lower. No vault mutation or deployment occurs.
