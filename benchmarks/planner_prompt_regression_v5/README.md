# Planner prompt regression v5

This is the current one-shot GPT-5.6 Luna / low production Planner regression gate after the
October 2026 prompt/cache compaction work.

It deliberately keeps the last still-current inherited cases from the v3 matrix, replaces the
obsolete journal/event fixtures with the three current Directorio Faro successors already
accepted by v4, and adds the real Odyssey regressions discovered since then:

- unresolved literal/group context must not swallow a nested typed identity;
- the nested rule is checked across person, project, document, and concept;
- mi mujer e hijos and the reverse order remain two independent relational scopes;
- an unknown complete relationship set remains a complete_set semantic identity for Core to
  ground/literalize safely rather than becoming a fake singular entity;
- the old unknown self-member project case is no longer an accepted failure because singular
  typed identity creation is now a human-approved generic product invariant.

The gate uses the real production-composed NoteSchema including Tasks, pins the exact current
Planner prompt, provider schema, teaching examples, and new-case registry, makes one provider call
per case, never retries, never calls Sol, and never mutates the vault.
