# Semantic WRITE identity and reference resolution

Status: **current WRITE contract layered on the Phase 15–17 planner/application foundations**

This note records the post-Reference-&-Relationship-v1 simplification of ordinary singular WRITE identity. Historical Phase 15/16 documents still describe why local reference indexes and pre-writer binding were introduced; they are not the current model-facing contract.

## Model/Core boundary

Luna interprets language. Core owns identity.

For each ordinary write Luna must preserve three things:

1. the semantic description of the entity that owns the new fact;
2. the new fact or mutation itself;
3. semantic descriptions of other entities mentioned by that fact and worth linking.

A target description such as `mi hijo al que le gusta el fútbol`, `la amiga con la que cené ayer`, an exact name, or another contextual identity phrase is a semantic query. Luna does not choose a stable Odyssey ID and does not count write-unit indexes.

The provider-facing reference shape is:

```text
KnowledgeReference
├─ mention
├─ role
└─ selection
   ├─ entity
   ├─ query
   ├─ type
   └─ filters
```

`target_index`, `self_target`, `link_scope`, and `relational_reference` are not provider fields inside a fact reference. The ordinary write target keeps the established full `SelectionCriteria` contract because direct self writes and bounded relational source writes still need those explicit semantics.

## Luna semantic WRITE frontend checkpoint

The current feature branch implements the first reversible **offline Luna-only adoption** of the
semantic WRITE boundary. Luna's WRITE prompt/schema now describe semantic operations; Sol retains
the exact legacy prompt and provider schema as the independent fallback. Both branches converge
immediately on the existing `RequestPlan` boundary, so the resolver, application, runtime, storage,
and materialization interfaces remain unchanged. The first live adoption gate failed on its first
case; the offline successor correction below still requires fresh live evidence.

```text
Luna semantic PLAN actions (provider order)
        |
        +-- retrieve/delegate --> established validators
        |
        `-- each semantic write.operations[]
                    |
                    v
             SemanticWriteIntent
                    |
                    v
          exactly one existing WriteAction
        |
        v
existing RequestPlan -> unchanged downstream behavior

Sol fallback -> frozen legacy prompt/schema -> existing RequestPlan
```

The semantic values preserve ownership, the full target description, explicit direct-name/type/filter evidence, `SELF`, genuine bulk intent, candidate-scope meaning, ordered facts, explicit property/tag/type mutations, and which fact spans denote other Odyssey identities. A candidate scope is deliberately generic and non-recursive: its source is either authenticated self or one existing source described in free text, plus a free-text member query and `one member | complete set` extent. This is not a relationship ontology.

Core deterministically derives the existing representation mechanics: local `{{ref:N}}` numbering, `KnowledgeReference` values, generic internal reference role, lookup-only units, target indexes, `source_kind` / `source_query` / `members`, and ordinary singular cardinality. The compiler immediately routes the resulting raw write shape through the existing `validate_request_plan()` path, so property, tag, type-migration, reference, bulk, and mutation invariants remain owned by the established validator. `all_matching` bulk and relational `complete_set` stay distinct semantic operations.

Candidate-scope source is a closed non-recursive union: authenticated `SELF`, or
`SOURCE_DESCRIPTION` with one bounded description. `SOURCE_DESCRIPTION` is deliberately not an
existence assertion: it records the source described by the request, while Core must resolve that
source against existing canonical evidence or clarify. Semantic objects are closed and fully required
for Structured Outputs. The wire contract cannot express units, cardinality, reference indexes,
lookup-only flags, roles, or relational source/member plumbing. The raw decoder rejects open or
correlated shapes; `compile_semantic_write()` remains authoritative for lowering and established
schema/mutation validation.

One provider write action owns its ordered `operations[]` and compiles independently to exactly one
existing `WriteAction`. Separate writes remain separate even when adjacent or separated by retrieve
or delegate actions. The compiler fails closed on mixed `one` / `all_matching`, multiple bulk
operations, multiple material relational targets, and `complete_set` combined with another material
operation. A semantic parse/compiler failure becomes bounded `RequestPlanningError`, allowing the
existing single normal Sol fallback. `ESCALATE` remains a clarification and never invokes Sol.

The frozen SWR registry, cases, oracles, and v8 evidence are unchanged. Provider-free tests cover all
nine compilable current SWR cases; SWR05 remains planner-owned escalation and never reaches the
compiler. `teaching_examples_v3.json` converts only WRITE examples to the semantic shape while
preserving generic READ/delegate lessons; v2 remains immutable.

### Provider-free measurements and gate status

Measured with the active schema and the frozen `2026-09-28 20:30 Europe/Paris` context:

| Input | `c6e4364` baseline | Offline checkpoint | Delta |
| --- | ---: | ---: | ---: |
| Sol prompt | 25,474 bytes | 25,474 bytes | 0 (byte/hash identical) |
| Sol provider schema | 47,418 bytes | 47,418 bytes | 0 (byte/hash identical) |
| Luna prompt | 32,076 bytes | 32,281 bytes | +82 (+0.26%) |
| Luna provider schema | 22,521 bytes | 18,539 bytes | -3,982 (-17.7%) |
| Luna WRITE schema branch | 7,343 bytes | 3,378 bytes | -3,965 (-54.0%) |

These are contract-size measurements, not latency evidence. The old-contract v9 runner is
permanently retired before provider construction. The consumed `semantic-write-frontend-v1` gate
reused the ten active SWR cases plus three generic READ/delegate/mixed-order sentinels. It stopped
fail-fast on SWR01 after one completed Luna/low call: the target was correctly authenticated self,
but both safely selectable participants were left inside one literal fact, so Core received no
identity parts or references. The unchanged frozen oracle correctly rejected that loss of link
semantics.

The smallest v1 correction was one generic teaching example for the already-stated identity-part
rule. The authorized v2 gate then passed SWR01 and SWR02 but failed SWR03 after Luna preserved the
full friend description and fact while inventing `la cena de ayer` as an existing relational source.
That is a real model-facing regression, not an oracle defect: the request supplies event context but
does not establish an existing canonical dinner source, and the prompt already says not to invent
one. The contradiction was in the complete-set teaching example, which itself treated an implicit
dinner event as an existing source.

The v3 correction changed only that teaching example so its request explicitly identified an existing
Atlas project note before using `EXISTING_DESCRIPTION`. The authorized v3 gate then passed SWR01,
SWR02, and SWR03, confirming that correction, but stopped fail-fast on SWR04 because Luna returned
`ESCALATE` for `Mi hijo mayor fue al cine con la amiga que vive en Lyon.`. The semantic frontend can
represent that request safely: the older child is one relationship-bounded target and the Lyon friend
is one independently described fact identity. The unchanged frozen oracle is therefore retained.

The v4 correction added one generic non-held-out teaching example with unrelated vocabulary for that
already-stated distinction. The authorized v4 gate then passed SWR01 through SWR07 and stopped on
SWR08: Luna preserved the SELF-bounded daughter target and the full described companion, but the
companion lost its explicit existing-source relationship bound and became a global descriptive lookup.
That violates the frozen `bounded_companion_relation` oracle and would widen identity resolution beyond
the user's supplied source, so the oracle is retained.

The v5 correction strengthened that same generic teaching example. The authorized v5 gate again
passed SWR01-SWR07 and stopped on SWR08: the companion still lost its bounded event-source scope. The
run also exposed one over-constrained oracle detail: it required `mayor` inside the daughter relationship
anchor, while the deterministic semantic compiler intentionally uses `mi hija` as the candidate universe
and keeps `mayor` in the full target description. That oracle detail is corrected; the real
`bounded_companion_relation` failure remains unchanged.

The v6 correction refined the existing generic teaching example rather than adding prompt rules. The
authorized v6 gate passed SWR01-SWR03 but stopped on SWR04 because Luna made authenticated self the
owner of the child's cinema fact and represented the child as another fact identity. That regression
appeared only after retuning the teaching example to repair SWR08, while the earlier v4/v5 checkpoints
had repeatedly passed SWR01-SWR07. This is evidence of non-monotonic example tuning rather than a need
for more phrase-specific examples.

The architecture review therefore retires frontend-v7 **without provider calls** and restores the
teaching examples semantically to the known-best v5 checkpoint. The remaining SWR08 ambiguity is moved
into the semantic contract itself: provider-facing `EXISTING_DESCRIPTION` becomes
`SOURCE_DESCRIPTION`. Luna no longer has to claim that the source exists; it only describes the source
that bounds the identity, and Core remains responsible for grounding it against canonical evidence or
clarifying. The internal lowered `source_kind=existing` behavior is unchanged. No new teaching example,
relationship taxonomy, Core resolver rule, or mutation authority is added. Frontend-v8 reused the same 13 requests and pinned evaluator and deliberately continued after failed oracles to collect the complete matrix. The authorized run completed all 13 cases: **12 passed and only SWR07 failed**. SWR08 and SWR10 both passed under `SOURCE_DESCRIPTION`. SWR07 preserved the full qualified participant wording but omitted candidate scope, widening it to a global descriptive target instead of a bounded event-source member. The retained artifact SHA-256 is `49e3598e4f8fb8131bfd0122501160cf113ca4da952112207e7573fa2b98be61`; usage-backed estimated cost is `$0.00912232`. v8 is permanently consumed at zero authority. The remaining SWR07 behavior is accepted as a bounded degradation: the full descriptive target is still preserved and Core performs ordinary global semantic resolution, rather than adding case-specific prompt or resolver complexity.

## Possessives are identity evidence, not self authority

First-person possessive wording does not by itself select the authenticated self note.

```text
Mi hijo al que le gusta el fútbol adora el chocolate.
```

means:

```text
target.query = "mi hijo al que le gusta el fútbol"
fact         = "Adora el chocolate."
```

It must not become `target.self_target=self`. `self` is reserved for facts whose actual subject is the authenticated user, for example `Axel y Denis son mis compañeros de trabajo`.

For singular WRITE, `relational_reference` may be a **candidate anchor** rather than the final identity decision. Its source-relative `reference` defines the bounded current relationship universe; `target.query` still preserves the user's complete description and may contain additional qualifiers. Core first grounds every relevant current relationship fact (including incoming backlinks), projects only identities actually linked by those facts, and then evaluates the full `target.query` only inside that grounded universe. The relationship can therefore narrow `mi hija a la que le gusta ver detectives de animales` to current children before the richer description selects one child. A global semantic candidate cannot enter that second-stage decision.

Bare singular relationship targets keep the established direct path. `complete_set` writes remain stricter: their relational reference must still describe the complete requested set rather than a qualified subset, because that path writes one shared source fact for the whole grounded set.

## Resolution

Core resolves a semantic target or reference against current canonical evidence:

```text
semantic query
  -> exact/local semantic candidates
  -> bounded current relationship evidence when useful
  -> contextual Luna selection over supplied candidates
  -> one canonical stable identity or abstention
```

The contextual model may select only IDs supplied by Core. No similarity score, possessive phrase, or planner field is itself mutation authority.

When a descriptive query carries a relational anchor, Core treats canonical structure and semantic interpretation as separate steps: relationship facts define the candidate universe; the full query chooses at most one member. Candidate evidence includes the canonical note body plus current incoming backlink facts, so information stored on another Note but linked to the candidate participates in identity resolution without copying knowledge or treating an index as authority. The same rule applies to `self` sources and named/existing sources such as `los amigos de Bruno`.

Known tombstoned link targets (`deleted: true`) are not current identities and therefore cannot enter or block a qualified singular relationship candidate set. Core keeps the containing fact inside the evidence guard, ignores only the inactive target for candidate narrowing, and still fails closed for malformed, ambiguous, or genuinely missing links whose identity state cannot be established. Complete-set semantics remain stricter and never treat a partial active subset as complete.

For qualified singular WRITE relationship anchoring, only the selector's supplied fact IDs carry relevance authority. They must be unique IDs from the exact Core-supplied batch. The reusable semantic-set response also contains character-span occurrence decorations, but those spans do not grant identity or mutation authority on this WRITE path and are not revalidated as relational proof; every chosen fact is instead re-read from canonical Markdown and its link targets are projected by Core before it can narrow candidates. This avoids making a harmless model span offset a false WRITE failure boundary while preserving the stricter occurrence checks on existing relational READ.

## Fact references

Provider references are lowered inside Core to the established deterministic reference-binding machinery. This lowering is an implementation bridge only: Luna never emits the local target indexes or lookup-only helper units.

A semantic fact reference first resolves against current canonical identities. If it resolves to exactly one existing note, Core binds that identity without mutating the referenced note. If no existing identity is found and the reference carries a canonical Odyssey note type, the normal WRITE creation contract may create that entity and then bind the new canonical path into the source fact. This is how a phrase such as `el proyecto Faro` can create a `project` note when `project` is a canonical schema type.

Once a reference is resolved, durable Markdown always renders the referenced note's canonical `name` as the wikilink display text. Descriptive occurrence wording remains resolution/clarification evidence only; it is never promoted into a durable alias implicitly. For example, `la persona de la cena relacional de prueba que trabaja en Airbus Test` may resolve to `Marta Test`, but the persisted link is `[[people/marta-test|Marta Test]]`. Unresolved references retain their original wording only while clarification is still required.

The active `note-schema` is the authority for that creation vocabulary. Core must not add a second hidden ontology such as a separate "concrete enough" test. Types whose semantics belong to future applications stay out of the active registry until those applications define them; an inactive type cannot silently become CREATE authority.

A new entity created only to satisfy a semantic fact reference is dependency-atomic with the fact that consumes it. Core may preflight and materialize dependencies first, but if no consuming source fact ultimately materializes, the just-created revision-1 helper is revalidated and rolled back before the request is committed or the derived index is refreshed. Independent successful branches may still remain `PARTIAL`; this is not whole-request transactional rollback.

If existing evidence is ambiguous, Core still defers for clarification rather than creating a duplicate or guessing. If unresolved reference wording has no canonical note type, Core has no creation authority; non-entity context should remain literal fact text rather than being promoted to a reference.

Legacy pre-existing index-based internal fixtures may retain their historical non-blocking pending behavior while migration is incomplete. That compatibility path must not re-enter the provider schema.

## Deferred ambiguity explanation

The current contextual resolver can safely return `RESOLVED`, `AMBIGUOUS`, or `UNRESOLVED`, but `AMBIGUOUS` does not yet carry the smaller set of candidates the model considered genuinely plausible. The application therefore cannot reliably explain a conflict such as "Cloe and Bruno Test both match this description" without risking presentation of unrelated candidates from the broader retrieval set.

A later focused change should let an ambiguous contextual decision return a validated subset of supplied `candidate_ids` together with enough grounded source evidence for a useful user-facing clarification. Core must verify every returned ID was in the supplied candidate set and must never manufacture the explanation from semantic rank alone. This is a model-facing contract change and requires its own deterministic fail-closed coverage and focused live gate; it is intentionally not part of the current atomicity/schema amendment.

## Required sentinels

The focused contract must keep deterministic coverage for at least:

- `Axel y Denis son mis compañeros de trabajo` — self is the subject; both coworkers are semantic fact references and participant notes are not reciprocally mutated;
- `Mi hijo al que le gusta el fútbol adora el chocolate` — use the child relationship as a bounded candidate anchor when available, preserve the full qualifier, and update the resolved child rather than self;
- `La amiga con la que cené ayer se muda a París` — resolve a contextually described target;
- `Mi hijo mayor fue al cine con la amiga que vive en Lyon` — relationally narrow the described child target, then resolve the described fact reference independently;
- `El amigo de Bruno que vive en Lyon se muda a Toulouse` — ground Bruno first, admit friend candidates from Bruno's outgoing facts or incoming backlinks, and apply the Lyon qualifier only inside that set;
- a genuinely ambiguous reference — defer for clarification without guessing, creating an identity, or writing a falsely settled source fact.

The provider-facing schema/prompt change requires focused live evidence under `AGENTS.md`. That live gate is Luna/low only, planner-only, zero retries, zero Sol fallbacks, cost-gated, non-overwriting, and separate from deterministic Core execution tests.

## Live-gate status

The user authorized semantic-write-frontend-v1 at its `$0.1594554` conservative ceiling. It ran
once at authorization commit `6985314` and stopped fail-fast on SWR01 after exactly one completed
Luna/low call, zero retries, and zero Sol calls. The retained one-row artifact SHA-256 is
`4431ba7ca547aa3c82070d20f4c391b2113cb4ce8b9754d88e0ddefb1018ebfa`; usage was 9,073 input,
125 output, and 0 reasoning tokens, for a checked-in-pricing estimate of `$0.0019646`.

The user then authorized semantic-write-frontend-v2 at its `$0.162357` conservative ceiling. It ran
once at authorization commit `8caa17c`, passed SWR01 and SWR02, and stopped fail-fast on SWR03 after
three completed Luna/low calls, zero retries, and zero Sol calls. The retained artifact SHA-256 is
`5b2cbe8fa4b1cdc6936968d9f54d9f1a377d3badcdaeeba388f97df5e1147edd`; the usage-backed
checked-in-pricing estimate is `$0.00308352`.

The user then authorized semantic-write-frontend-v3 at its `$0.1626716` conservative ceiling. It ran
once at authorization commit `be0976c`, passed SWR01-SWR03, and stopped fail-fast on SWR04 after four
completed Luna/low calls, zero retries, and zero Sol calls. The retained artifact SHA-256 is
`ff1c88f2cb29613009f943f73cba61cbcb2a00b613acca75207070771d93f8fc`; the usage-backed
checked-in-pricing estimate is `$0.00360986`.

The user then authorized semantic-write-frontend-v4 at its `$0.1657318` conservative ceiling. It ran
once at authorization commit `3fb65b7`, passed SWR01-SWR07, and stopped fail-fast on SWR08 after eight
completed Luna/low calls, zero retries, and zero Sol calls. The retained artifact SHA-256 is
`1963296cbcc857c0f07703b0b045ee411b3aabed826a4d689bf822ed9b975652`; the usage-backed
checked-in-pricing estimate is `$0.00631928`. The user then authorized v5 at `$0.1664832`. It also passed SWR01-SWR07 and stopped on SWR08 after eight Luna/low calls, zero retries, and zero Sol calls. Its retained artifact SHA-256 is `a94c33198b96bfbb152e3402ba04e7acba6fbeafff8e4b315fb9343c07d9987c`; usage-backed cost is `$0.00604402`. The user then authorized v6 at `$0.166712`. It passed SWR01-SWR03 and stopped on SWR04 after four Luna/low calls, zero retries, and zero Sol calls. Its retained artifact SHA-256 is `0a4b2524bda2605bcbcc6e4f7662090c0089e4c2cc264089ab83c3ecb9b0ab2e`; usage-backed cost is `$0.00380722`. The v1-v6 runners/paths are permanently consumed. Frontend-v7 was retired unexecuted after the design review. Frontend-v8 is also consumed: its complete matrix passed 12/13, with only SWR07 degrading to global descriptive resolution. A subsequent model-only comparison reused the exact same prompt, schema, cases, evaluator, and `low` effort on `gpt-6-luna`: 11/13 passed, with SWR07 fixed but SWR08 and SWR10 regressing by losing event-source bounds on fact references. The GPT-6 artifact SHA-256 is `896e73337a9a1ffbf2984b8db18c214d7dea03e8f705ad181b6950554a941628`; usage-backed estimated cost is `$0.00419596`. Despite the lower cost, the planner retains `gpt-5.6-luna` because its frozen-matrix accuracy is higher (12/13 vs 11/13).

After integration with the collection/clarification contract, the five-case Luna/low planner gate ran at commit `1f0047d` under an explicitly authorized `$0.070515` conservative ceiling and `58,227`-byte input bound. All five frozen cases passed with five Luna/low calls, zero retries, zero Sol calls, and an estimated actual cost of `$0.0044110`. That evidence remains historical evidence for that exact model-facing contract.

A manual DEV regression then exposed a distinct planner/Core boundary: for `Mi hija a la que le gusta ver detectives de animales adora el chocolate`, Luna preserved the full `target.query` and also emitted `relational_reference = "mi hija"`, but Core treated the relationship as a terminal one-fact decision and deferred before using the richer qualifier. A temporary exact-wording guard proved that the qualifier itself resolves correctly, but the durable design is stronger: keep the relationship as grounded candidate authority and use the complete query as the second-stage discriminator. This also generalizes to named sources and incoming backlinks instead of falling back to a vault-wide semantic search.

A subsequent retry of that same event-participant case exposed a separate Core source-resolution leak: the planner was now valid, but Core resolved `relational_reference.source_query` using the full qualified target query as semantic context. The target-only qualifier `Airbus Test` therefore biased local source ranking toward Marta/Airbus instead of the intended `Cena relacional de prueba` anchor. Existing relationship sources are now resolved against the relationship anchor wording itself (`relational_reference.reference`), while the full target query is reserved for the second-stage member discriminator. This keeps anchor identification and member qualification as separate semantic decisions.

A later manual event-participant WRITE exposed a planner cardinality/source-placement boundary before Core execution. The request targeted one qualified participant from a multi-member relationship source. Both Luna and the normal Sol fallback produced locally invalid relational selection (`RELATIONAL_REFERENCE_CONFLICT`), so zero mutation occurred. The planner contract now makes the distinction explicit: `members=one` describes the final selected identity even when the anchor universe contains several members, `complete_set` is reserved for requests targeting the whole relationship set, and an `existing` anchor source belongs only in `relational_reference.source_query` while `target.entity` remains null. The exact manual phrase is a frozen case in the pending current-contract gate.

The pending active-schema gate therefore uses a distinct registry that preserves the historical v1 evidence while covering the exact daughter regression, a generic existing-source case (`El amigo de Bruno que vive en Lyon...`), and the manual event-participant regression (`De las personas que estuvieron en la cena relacional de prueba...`). It now contains eight Luna/low planner cases and preflights at a conservative no-cache ceiling of `$0.1079632` with a `55,189`-byte input bound. The eighth case covers a relational target plus a separately described semantic reference so target identity wording cannot absorb the new fact payload. `MAX_COST_USD` remains `$0.00`; no provider call has been made for this amended contract and a fresh explicit authorization is required before running it.
