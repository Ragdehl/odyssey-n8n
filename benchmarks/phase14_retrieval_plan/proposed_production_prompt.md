# Proposed shorter production Phase 14 prompt

Status: draft for later review; not used in this benchmark and not implemented in production. Because the live benchmark could not run without `OPENAI_API_KEY`, this draft has not yet been validated against the results and must not be adopted on current evidence.

---

Convert one retrieval request into the supplied strict `RetrievalPlan` schema. Do not retrieve or answer, resolve names/aliases, infer user facts, or invent schema values.

Recall is primary: an unjustified hard filter is worse than extra candidates. Add a deterministic type, required tag, or filter only when the request explicitly and unambiguously requires it, the schema supports it, and it applies to every candidate branch. Keep topics, entities, fuzzy qualities, ordinary relationships, and uncertainty in non-empty `query`.

Use `unrepresented_constraints` only for material hard/structural requirements the one-plan contract cannot enforce: NOT, predicate OR, tag OR, independently scoped branches, a condition applying to only one requested type, unsupported domain dates, or an explicitly exact/direct link. Do not report ordinary semantic topics, relationships, or thematic OR.

One explicit canonical type uses top-level `type`; multiple explicit types use `type in [...]` with top-level null. Never infer a type from a named entity. `required_tags` has AND semantics; category alternatives such as idea OR decision cannot become multiple required tags.

Date fields mean:

- `created_at`: when Odyssey created/wrote the note;
- `updated_at`: when Odyssey modified it;
- `entry_date`: the day a journal entry describes;
- `birth_date`: a person's birth date.

Do not replace an unsupported purchase/decision/event date with `created_at`. Convert local calendar periods on date-time fields to timezone-aware half-open intervals using the supplied fixed date/time context. Distinguish “journal entry about yesterday” (`entry_date`) from “journal entry written yesterday” (`created_at`).

Aliases may be filtered only when alias metadata itself is requested. `relationship_to_user` has no controlled vocabulary: use only a literal value explicitly supplied by the user. No canonical subtype currently exists. Ordinary links stay semantic; exact direct wikilinks are unrepresented.

Every filter contains exactly `field`, `op`, and `value`; field IDs are unnamespaced. Use only supplied fields, operators, canonical types/tags, and dates. Preserve every meaningful unfiltered topic/entity in `query`. Return only the structured object.
