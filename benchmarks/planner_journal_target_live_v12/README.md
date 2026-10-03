# Planner Journal target live gate v12

> **Retained partial-failure evidence.** v12 ran once on `894c38ae65c9d93a7adf7f143548fb475b554814`. It must not be rerun or used as acceptance evidence for the revised contract.

v12 tested whether the schema-driven Core planner binds a `journal_entry` write to the semantic date named by the user, with no Journal-specific Core rule. Both GPT-5.6 Luna low calls emitted the correct exact `entry_date` target filter, so an older journal entry from another date could no longer be selected.

The `ayer` case also emitted `entry_date` as a write property and passed. The `hoy` case omitted that required property, so it would not be create-safe when no same-day journal entry exists. The gate therefore correctly failed overall.

Retained evidence: 2 provider attempts, 2 completed responses, zero retries, no Sol fallback, estimated cost $0.00480240 Standard / $0.00528264 regional. v13 strengthens only the canonical `note-schema` guidance so a journal record write carries the same semantic date both as target identity evidence and as the required creation property.
