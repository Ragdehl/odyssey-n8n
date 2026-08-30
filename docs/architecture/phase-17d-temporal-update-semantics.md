# Phase 17D append-first atomic facts and correction/removal semantics

Status: **current implementation contract after Phase 17C and before Phase 17E / the first real Phase 18 E2E**

## Objective

Make ordinary Odyssey knowledge accumulation **atomic, append-first, traceable, and human-readable** without moving to one Markdown file per fact and without relying on free-form LLM body rewrites for normal updates.

The physical source of truth remains one canonical Markdown note per entity. Inside that note, ordinary knowledge is represented as individually addressable facts correlated to the logical Odyssey request that created them.

```text
one entity Markdown note
        |
        +--> sparse structured state when it unlocks useful behavior
        |
        `--> append-first atomic facts
                |
                +--> request-correlated provenance
                +--> human-visible capture chronology
                +--> duplicate suppression
                `--> targeted correction/removal when explicitly required
```

This contract supersedes the earlier Phase 17D implementation direction that tried to distinguish transition/correction/ordinary primarily so a bounded writer could safely rewrite free-form Markdown spans. Focused live evidence showed that the existing semantic `facts` channel was not a sufficiently reliable discriminator for destructive rewriting. The simpler solution is to avoid destructive rewriting for ordinary new knowledge.

The governing rule is:

> **New true knowledge normally appends. Previously true knowledge survives. False or explicitly removed knowledge may be targeted and removed/corrected.**

See [Odyssey knowledge-model direction](knowledge-model-direction.md) for the broader product rationale, schema-utility rule, emergent-schema direction, relinking constraints, and retrieval hypotheses.

## 1. One note per entity, atomic facts inside it

Do not create one Markdown file per fact. Stable entity identity, wikilinks, Obsidian interoperability, current properties, and application access remain centered on the entity note.

Within the body, however, every new independently meaningful piece of user knowledge should be represented as one atomic fact.

Example user request:

```text
"Marta trabaja en Thales, tiene dos hijos y se va a mudar a Lyon."
```

The validated write plan should preserve three independent facts rather than one compound fact string:

```text
fact 0  Marta trabaja en Thales.
fact 1  Marta tiene dos hijos.
fact 2  Marta se va a mudar a Lyon.
```

Atomicity matters because later duplicate detection, retrieval, correction/removal, provenance, and possible fact-level indexing need to address one unit of knowledge without rewriting unrelated content.

A fact does not need an unrelated generated UUID. Within one note, the minimal durable locator is
derived from the already-established logical `request_id` plus a deterministic plan fact ordinal.
For `all_matching`, one planned fact may materialize in several notes; a derived global key is
`(note_id, request_id, ordinal)`. The hidden marker keeps only request and ordinal because its
containing note already supplies `note_id`.

```text
request R123
  +--> R123:0
  +--> R123:1
  `--> R123:2
```

The ordinal must be deterministic from the validated plan order, not from successful-write order, so retries/partial execution cannot silently allocate a different locator for the same planned fact.

The locator is machine-facing and should not clutter normal reading.

## 2. Canonical human-readable rendering

The body should expose capture chronology clearly enough that a human reading the Markdown can understand that knowledge was added at different times.

Conceptually:

```markdown
# Marta

## Añadido el 12 de marzo de 2026

- Trabaja en [[Airbus]].
  <!-- odyssey:fact request=<request_id> ordinal=0 -->

## Añadido el 29 de agosto de 2026

- Ahora trabaja en [[Thales]].
  <!-- odyssey:fact request=<request_id> ordinal=0 -->
- Tiene dos hijos.
  <!-- odyssey:fact request=<request_id> ordinal=1 -->
```

The exact localized wording of the visible capture heading is presentation policy; the machine parser must not depend on natural-language heading text for identity/provenance. The hidden fact marker is the durable machine correlation.

A single request may create facts in several notes. The same planned ordinal may recur in different
notes for `all_matching`, while remaining unique within each containing note/request pair.

Do not embed Git commit SHAs in facts. The correlation remains:

```text
fact locator
  -> request_id
  -> Phase 17C commit trailer
  -> Git commit / audit time
```

### Capture time is not domain time

The visible capture date tells the human when Odyssey recorded the information. It must not be treated as the date the described event occurred.

```text
captured_at != happened_at
```

If the user says:

```text
"Marta empezó a trabajar en Thales en marzo."
```

then `en marzo` remains part of the fact. Odyssey must not invent an exact transition date from request time, Git time, or `updated_at`.

No redundant per-fact `recorded_at` property is required merely because the note displays capture chronology if request/Git provenance already reconstructs that time reliably.

## 3. Append-first mutation model

The physical body mutation vocabulary should remain as small as possible.

```text
ADD        append one new atomic fact
NO_CHANGE  do not append a clearly duplicate fact
REMOVE     remove one safely identified false/explicitly deleted fact
```

`CORRECT` is a semantic user operation, not necessarily a separate physical mutation primitive. A correction can be composed as:

```text
REMOVE old false fact
+
ADD corrected fact
```

This keeps canonical knowledge free of information known to be false while Git retains audit/recovery history.

Do not introduce `historical`, `current`, `retracted`, universal event-state flags, temporal arrays, or event sourcing merely to encode ordinary real-world evolution.

### Real-world transitions

A real-world transition normally requires no special destructive operation.

Before:

```markdown
## Añadido el 12 de marzo de 2026
- Trabaja en [[Airbus]].
```

User:

```text
"Marta ahora trabaja en Thales."
```

After:

```markdown
## Añadido el 12 de marzo de 2026
- Trabaja en [[Airbus]].

## Añadido el 29 de agosto de 2026
- Ahora trabaja en [[Thales]].
```

The Airbus knowledge remains canonical because it may have been true. The later fact and its wording/capture chronology provide the new evidence.

This is intentionally different from trying to rewrite `Trabaja en Airbus` into `Trabajaba en Airbus`. Human and model readers can interpret the chronology without Odyssey continuously polishing old prose.

## 4. Planner contract

The planner should preserve one independently meaningful item per `facts[]` entry.

It must not combine unrelated knowledge into a single fact merely because it arrived in one sentence/request.

Existing reference binding remains unchanged: semantic references inside facts use the established in-plan reference markers and are bound before canonical Markdown rendering.

### Properties do not replace conversational knowledge facts

The previous planner rule said that a fact fully represented by a canonical property should normally be omitted from `facts` to avoid duplication. Phase 17D narrows that rule for knowledge-bearing conversational capture.

When the user supplies knowledge that both:

1. is meaningful human knowledge worth retaining; and
2. safely maps to a registered canonical property,

the structured property may represent current deterministic state **and the user knowledge should still remain as an atomic fact**.

Conceptually:

```text
user knowledge
  "Marta ahora es mi jefa."
        |
        +--> fact: "Ahora es mi jefa."
        |
        `--> property projection: relationship_to_user = "jefa"
```

This prevents current structured state from silently erasing the human knowledge/history that produced it.

This rule is for knowledge-bearing conversational capture. Future domain applications may have purely operational state transitions (for example an internal workflow flag) where a property-only mutation is more appropriate; that application-specific behavior is not generalized in Phase 17D.

Do not invent unregistered properties such as `employer` or `residence` merely because a fact contains those concepts.

## 5. Ordinary existing-note writes should not require the bounded body writer

For an already-resolved existing note, an ordinary new atomic fact should follow a deterministic path:

```text
validated/bound fact
      |
      +--> exact/reliable duplicate? -> NO_CHANGE
      |
      `--> new knowledge -> deterministic ADD fact block
```

The generic Luna bounded writer should not be called merely to decide how to weave ordinary new knowledge into existing prose.

This is a deliberate simplification and cost reduction compared with the Phase 16 UPDATE path.

The existing writer remains relevant only where genuinely semantic targeting is still needed, especially legacy free-form body correction/removal until legacy content has a separate migration contract.

## 6. Duplicate suppression

Append-first must not mean append-everything.

At minimum, deterministic exact-normalized duplicate detection should operate over parsed atomic facts rather than arbitrary body lines.

```text
same canonical fact already present
        -> NO_CHANGE
```

Do not use MiniLM/cosine thresholds as autonomous duplicate or write authority. Earlier fragment-level evidence showed that semantically related independent knowledge can score too similarly for a safe universal threshold.

A later semantic duplicate/near-duplicate policy requires separate evidence if exact normalization proves insufficient.

## 7. Correction and explicit removal

A user may establish that prior knowledge was false or explicitly request its deletion.

Examples:

```text
"Me equivoqué: Marta nunca trabajó en Airbus; trabaja en Thales."
"Borra lo de que Marta tiene dos hijos."
```

Odyssey must identify the relevant atomic fact safely before removal.

Preferred resolution order:

```text
known fact locator
    -> deterministic target

else unique exact-normalized fact match
    -> deterministic target

else bounded semantic fact selector over the already-resolved note
    -> returns fact locator(s) or explicit no-match/ambiguity

ambiguity
    -> fail closed / pending work
```

The semantic model must select from supplied fact locators; it does not receive authority to rewrite arbitrary Markdown spans.

For a correction, once the false fact is safely identified:

```text
REMOVE false fact
ADD corrected atomic fact(s)
```

For explicit removal:

```text
REMOVE safely identified fact
```

Existing whole-note soft DELETE remains a separate Phase 16.7B operation.

## 8. Structured properties during append-first updates

Registered property mutations remain deterministic Core behavior.

When conversational knowledge establishes a new current property value:

```text
old property -> new property
new knowledge -> appended fact
old facts -> remain unless explicitly false/removed
```

Example, if the schema supports it:

```text
before
  relationship_to_user = "compañera"
  fact: "Es mi compañera de trabajo."

user
  "Ahora es mi jefa."

after
  relationship_to_user = "jefa"
  old fact remains
  new fact appended
```

No historical property array is introduced.

If an older property value exists only in legacy metadata with no corresponding body fact, Phase 17D must not invent a historical natural-language fact solely from that metadata. The structured value can still change; preserving synthetic metadata history as prose is deferred unless real evidence requires it.

This intentionally avoids the earlier proposed writer behavior that would manufacture a historical sentence from an old property value.

## 9. CREATE behavior

CREATE remains deterministic.

For a newly created entity:

1. allocate/validate identity/path through existing preflight;
2. render each prepared atomic fact deterministically under the request's capture section;
3. include the hidden request-derived fact locator;
4. apply deterministic registered properties/tags as already authorized;
5. persist through existing revision/schema validation;
6. let Phase 17C create the request-level Git commit after successful application execution.

No generic CREATE LLM writer is introduced.

The application boundary therefore needs to propagate the existing `request_id` (and deterministic fact ordinals) to materialization/rendering.

## 10. Legacy body compatibility

Do not automatically rewrite the user's existing vault into atomic facts as part of Phase 17D.

Existing pre-17D free-form body content remains readable canonical knowledge. New ordinary facts may append in the new fact format below legacy content.

Do not run a broad model-based migration over real user data.

Where a correction/removal explicitly targets legacy free-form content, the existing bounded writer path may remain as a compatibility fallback until a later migration/normalization contract is justified. New fact-aware content should use locator-based targeting instead.

Test fixtures and disposable benchmark vaults may be migrated as needed to exercise the new canonical path.

## 11. Retrieval/index compatibility

Phase 17D does not switch production semantic retrieval to fact-level embeddings.

The current semantic index may continue embedding the complete canonical note projection so Phase 17D can land without coupling knowledge-format changes to an unproven retrieval optimization.

Phase 17E will benchmark:

```text
whole-note MiniLM
vs
fact-level MiniLM
vs
combined entity + fact retrieval
```

Fact locators/rendering should therefore be parseable enough that derived indexes can later address facts independently, but the retrieval experiment must not block the Phase 17D write model.

## 12. Request-level safety and retries

The established application invariants remain intact:

- one stable `request_id` per logical request;
- partial success is explicit and not rolled back;
- Phase 17B pending work remains separate durable non-knowledge state;
- Phase 17C Git history remains request-level audit/recovery infrastructure;
- stable identity/path/reference validation remains deterministic;
- whole-note revision guards remain authoritative for persistence;
- no hidden chain of thought is stored.

Fact ordinals must be deterministic from the validated request plan so a resumed/retried logical request does not allocate different fact locators merely because earlier units succeeded or failed differently.

## 13. Focused model evidence

Phase 17D materially changes planner/model-facing behavior, so focused live evidence remains required under `AGENTS.md`.

Production configurations remain:

```text
planner: gpt-5.6-sol / low
semantic fact selector (if needed): gpt-5.6-luna / medium
```

Do not benchmark alternative models unless the production configuration fails the approved contract.

Live planner evidence should demonstrate at least:

- one user request with several independent facts is split atomically;
- ordinary new knowledge remains recordable without destructive-correction semantics;
- a knowledge-bearing registered property still retains an appropriate fact;
- unregistered concepts remain facts rather than invented properties;
- explicit correction/removal meaning is preserved enough to enter the targeted correction/removal path;
- existing reference markers/binding behavior remains correct.

If the new semantic fact selector is needed, focused live evidence should demonstrate selection/no-match/ambiguity over bounded fact locators without returning arbitrary Markdown edits.

Do not rerun the superseded temporal rewrite benchmark as the acceptance test for ordinary updates. Preserve its result as evidence explaining why the architecture changed.

## 14. Acceptance criteria

Phase 17D is complete only when deterministic tests and required focused live evidence show that:

1. One canonical Markdown file remains the source of truth for one entity.
2. New independently meaningful knowledge is represented as independently addressable atomic facts.
3. Fact locators are derived from `request_id` plus deterministic request-plan ordering without unrelated fact UUIDs.
4. Human-readable capture chronology is visible without confusing capture time with domain/event time.
5. Ordinary existing-note knowledge appends deterministically without a generic body-writer call.
6. Exact/reliable duplicates do not accumulate.
7. Real-world transitions do not erase older true knowledge merely because a newer fact exists.
8. Explicit false knowledge can be safely targeted and removed/corrected.
9. Explicit removal can safely target one fact without rewriting unrelated facts.
10. Corrections can be represented as removal of false fact(s) plus addition of corrected fact(s); no generic `CORRECT` storage primitive is required.
11. Knowledge-bearing conversational property mutations retain their corresponding human fact while registered properties remain deterministic current structured state.
12. No unregistered ontology fields are invented.
13. Existing wikilink/reference-binding safety remains intact.
14. Existing revision, schema validation, pending-work, request-level Git history, and partial-success semantics remain intact.
15. Legacy free-form body content remains readable and is not automatically migrated over real user data.
16. Production retrieval remains compatible; fact-level embeddings are deferred to Phase 17E evidence.
17. No event store, temporal database, history ontology, universal fact status model, or new infrastructure is introduced.

## Out of scope

- one Markdown file per fact;
- event sourcing or bitemporal storage;
- universal `current/historical/retracted` fact states;
- storing Git SHA or redundant per-fact timestamps as canonical fact metadata;
- automatic broad semantic deduplication;
- automatic migration of all legacy user notes into atomic facts;
- fact-level production embeddings before Phase 17E benchmark evidence;
- emergent-schema implementation/backfill/relinking (Phase 17E defines the checkpoint/direction; later implementation is evidence-driven);
- filesystem watcher/manual-edit ingestion (Phase 19);
- user-facing timeline UI.

## Architecture challenge result

`RECONSIDER` the superseded free-form temporal rewrite implementation.

Material concern: the earlier approach kept ordinary UPDATE centered on LLM span rewriting and required an explicit transition/correction/ordinary discriminator to prevent destructive replacements. That adds semantic and mutation complexity to solve a problem that append-first storage can mostly avoid.

Simpler alternative: make ordinary knowledge atomic and append-first; use deterministic ADD/NO_CHANGE; reserve targeted REMOVE plus ADD for explicit false-knowledge correction; use bounded model reasoning only to select a fact locator when deterministic targeting is insufficient.

Trade-offs: the body needs a small parseable fact marker and capture-section renderer; conversational property knowledge may be intentionally represented both as human fact and structured current state; legacy free-form content temporarily needs a compatibility path.

Recommendation: proceed with the atomic append-first contract and preserve the old temporal benchmark/implementation only as superseded evidence, not as the production design.

Human decision required: **NO** — the merged knowledge-model direction already resolves the material product decision.
