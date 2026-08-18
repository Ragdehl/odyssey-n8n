# Odyssey Architecture

## Purpose

Odyssey turns arbitrary user messages into reusable personal knowledge and grounded retrieval.
Markdown files remain authoritative and human-readable; Python owns note and domain behavior; n8n
owns integration and orchestration. The system adds infrastructure only when an observed requirement
cannot be met by these boundaries.

A message is not assumed to represent one note or one operation. It may ask a question, provide or
modify knowledge, describe several subjects, include a task or event, or combine retrieval and
writing.

## Capability hierarchy

This is a conceptual capability map, not a mandatory pipeline. Retrieval does not traverse the
write branch, and a mixed request may use both branches. A `KnowledgeUnit` is a knowledge object,
not necessarily an entity: only entity references that require identity lookup pass through
`resolve_entity`.

```text
USER / AGENT
     |
     v
interpret_request                 [PLANNED]
     |
     +-------------------------------+
     |                               |
     v                               v
RETRIEVAL INTENT                WRITE INTENT
     |                               |
     v                               v
get_context                    decompose_knowledge
  [PLANNED]                       [PLANNED]
                                     |
                                     v
                               KnowledgePlan
                                     |
                          +----------+-----------+
                          |                      |
                          v                      v
                  Knowledge units       entity references that
                  and their facts       require identity lookup
                          |                      |
                          |                      v
                          |               resolve_entity
                          |                  [PLANNED]
                          |                      |
                          |                      v
                          |          resolve_exact_entity
                          |                   [PHASE 9]
                          |                      |
                          |                      v
                          |     find_exact_entity_candidates
                          |                   [PHASE 9]
                          |                      |
                          |                      v
                          |   find_semantic_entity_candidates
                          |                  [PHASE 10]
                          |                      |
                          +----------+-----------+
                                     |
                                     v
                       planned domain/write decisions
             create_entity / update_entity / save_knowledge [PHASE 12]
                                     |
                                     v
                          validated Note persistence
```

A purchase, event, task, journal entry, or document remains knowledge in its own right. For
example, a purchase unit sends its store and product references to identity resolution while its
purchase facts remain attached to the purchase:

```text
Purchase unit
    |
    +--> store reference ----> resolve_entity("Carrefour Balma", type="store")
    |
    +--> product reference --> resolve_entity("Lactel", type="product")
    |
    +--> purchase facts ------> remain purchase knowledge
```

After the referenced identities are settled, later planned domain behavior may construct and save
the purchase. Odyssey does not yet permanently classify every possible unit or implement a generic
routing framework.

The Phase 9 call direction is the exact layer only:

```text
resolve_exact_entity
      |
      v
find_exact_entity_candidates
      |
      +--> VaultRepository.list_markdown_paths
      +--> VaultRepository.read_text
      +--> parse_note
      +--> validate_note
```

The Phase 10 semantic layer is a separate candidate-only fallback over a disposable derived index:

```text
SemanticEntityIndex.rebuild
      +--> list/read authoritative Markdown
      +--> parse and validate every Note
      +--> build one retrieval projection per note
      +--> local multilingual embedding
      +--> atomically replace derived SQLite index

find_semantic_entity_candidates
      +--> embed reference + caller context locally
      +--> optional canonical type filter
      +--> exact cosine ranking
      +--> Top N candidate evidence (never an identity decision)
```

Read and write transformations run in opposite directions:

```text
READ
VaultRepository.read_text
    -> raw Markdown
    -> parse_note
    -> Note
    -> validate_note

WRITE
planned domain / knowledge outcome
    -> Note
    -> validate_note
    -> serialize_note
    -> raw Markdown
    -> VaultRepository.create_text / future update boundary
```

`parse_note` never writes, `serialize_note` never reads, and `validate_note` can participate in
either direction. `VaultRepository` remains raw filesystem access: it does not parse Markdown, load
schema meaning, discover identity candidates, resolve identities, or make domain decisions.

## Capability contracts

Every conceptual output below is illustrative unless the capability is marked implemented. Phases
9 and 10 do not freeze request-plan or knowledge-plan Python APIs or JSON schemas.

### `interpret_request` — understand the requested operations

- **Purpose:** understand what the user wants and plan one or more retrieval or write operations.
- **Input:** the original message and applicable conversation context.
- **Output:** a conceptual request plan which may be retrieval-oriented, write-oriented, or mixed.
- **Can see:** original user language and caller-supplied conversational context.
- **Must not know or do:** open Markdown files, resolve identity, decide that a referenced entity
  exists, or decide to create a new entity.
- **Status:** **PLANNED**. `RETRIEVE`, `WRITE`, and `MIXED` describe expected outcomes without
  freezing an enum or permanent API.
- **Concrete conceptual example:**

  Input:

  ```text
  What did I pay for Lactel last time?
  Also remember that I bought two bottles today at Carrefour.
  ```

  Output:

  ```text
  RequestPlan
    retrieval:
      - previous Lactel purchase price
    write:
      - today's purchase of two Lactel bottles at Carrefour
  ```

  This is a mixed request. Interpretation may identify a store reference with
  `name="Carrefour", type="store"`; only the later resolver can determine whether it exists.

### `get_context` — retrieve relevant knowledge

- **Purpose:** assemble knowledge relevant to a user or application question.
- **Input:** a retrieval intent such as `previous Lactel purchase price`.
- **Output:** a future context package grounded in Odyssey notes.
- **Can see:** the interpreted question and results from future retrieval capabilities.
- **Must not know or do:** equate semantic relevance with entity identity or mutate notes.
- **Status:** **PLANNED**. Phase 10's entity-candidate index does not define general knowledge
  retrieval, linked-note traversal, or the future context-package contract.
- **Concrete conceptual example:** input `previous Lactel purchase price`; output might identify the
  source purchase note and a recorded price, with enough provenance to answer the user. The exact
  package shape remains undecided.

### `decompose_knowledge` — build related knowledge work

- **Purpose:** transform the write-oriented part of a request into related conceptual knowledge
  units while retaining relationships and required context.
- **Input:** interpreted write intent and applicable request context.
- **Output:** a conceptual `KnowledgePlan` containing related `KnowledgeUnit` values.
- **Can see:** write intent, subjects, facts, relationships, and context supplied by interpretation.
- **Must not know or do:** split text into unrelated fragments, resolve identities, choose storage
  paths, write notes, or freeze a permanent plan schema.
- **Status:** **PLANNED**. `KnowledgePlan` and `KnowledgeUnit` are architecture vocabulary only.
- **Concrete conceptual example:**

  Input:

  ```text
  Today I bought Lactel milk at Carrefour Balma.
  Carrefour Balma closes at 21:00.
  Lactel is my usual milk.
  ```

  Output:

  ```text
  KnowledgePlan
    Unit A:
      subject: Carrefour Balma
      type: store
      facts:
        - closes at 21:00
    Unit B:
      subject: Lactel
      type: product
      facts:
        - usual milk
    Unit C:
      type: purchase
      references:
        store -> Unit A
        product -> Unit B
      facts:
        - occurred today
  ```

Information about one subject is grouped even when it occurs in separate sentences. For example,
closing time, normal Saturday visits, and parking information about Carrefour Balma belong to one
unit rather than three sentence fragments. A unit may reference another unit instead of duplicating
all context into every future note.

### Parallel and ordered plan processing

Future orchestration may parallelize independent, read-only work:

```text
KnowledgePlan
    |
    +---- Carrefour reference ---- resolve_entity ----+
    |                                                 |
    +---- Lactel reference ------- resolve_entity ----+  PARALLEL OK
    |                                                 |
    +---- another entity reference -> resolve_entity -+
```

Dependencies still determine ordering:

```text
resolve Carrefour
      |
      v
create Purchase referring to Carrefour identity
```

Only references requiring identity decisions are resolved; a knowledge unit is not passed wholesale
to `resolve_entity`. Several facts targeting the same logical entity must be coalesced before
mutation rather than race as independent writes. The rule is: parallelize independent work;
serialize or coalesce dependency-sensitive and same-entity mutations. This property does not
require or authorize a DAG engine, scheduler, LangGraph, workflow engine, or parallel execution
framework in Phases 9 or 10.

### `create_entity` / `update_entity` — persist explicit entity decisions

- **Purpose:** persist an explicit caller decision as a validated canonical entity note.
- **Input:** an explicit create request or path-plus-ID-guarded metadata/body mutation.
- **Output:** a deterministic created, updated, or no-change result.
- **Can see:** caller-decided domain metadata/content, lifecycle inputs, and the canonical schema.
- **Must not know or do:** infer meaning, resolve identity, treat `UNRESOLVED` as creation
  permission, or perform an automatic update-or-insert.
- **Status:** **IMPLEMENTED** in Phase 12; future orchestration composes these operations.

### `save_knowledge` — persist approved knowledge changes

- **Purpose:** coordinate validated creations, updates, and links from resolved knowledge units.
- **Input:** dependency-aware knowledge work after required identity and upsert decisions.
- **Output:** a future summary of knowledge saved or requiring clarification.
- **Can see:** approved domain outcomes and note-domain contracts.
- **Must not know or do:** manipulate raw files directly, ignore dependencies, or invent ontology
  schema.
- **Status:** **PLANNED**; Phase 10 does not implement its write behavior.
- **Concrete conceptual example:** after store and product identities are settled, save a purchase
  note linking those entities and report the affected notes. Exact contracts remain a future
  architecture decision.

### `resolve_entity` — layered hybrid identity resolution

- **Purpose:** eventually resolve an entity reference by composing exact lookup, cheap structured
  narrowing, semantic retrieval, and contextual reasoning while preserving uncertainty.
- **Input:** an extracted reference, original surrounding request context, repository/schema access,
  and any available deterministic constraints.
- **Output:** a future resolved, ambiguous, or unresolved outcome with supporting evidence.
- **Can see:** the original reference and context plus evidence returned by its lower layers.
- **Must not know or do:** equate semantic similarity with identity, invent certainty, authorize
  automatic creation after no exact match, or make an LLM scan the entire vault.
- **Status:** **PLANNED** for contextual resolution after Phase 10. No Python function with this
  name exists yet.
- **Concrete conceptual example:** `"the other Beatriz"` may have no exact match. Structured and
  semantic retrieval may narrow candidates to the user's spouse and Xavi's partner; contextual
  evidence may resolve the latter or retain ambiguity when evidence is insufficient.

```text
reference + original request context
                |
                v
       resolve_exact_entity
                |
       +--------+----------------+
       |                         |
unique exact match       no/ambiguous exact match
       |                         |
       v                         v
    resolved          structured candidate narrowing
                               [PLANNED]
                                  |
                                  v
                         semantic/vector retrieval
                              [PHASE 10]
                                  |
                                  v
                    strong contextual reasoner
                               [APPROVED DIRECTION]
                                  |
                       +----------+----------+
                       |          |          |
                    resolved   ambiguous   unresolved
                       |          |          |
                       +----------+----------+
                                  |
                                  v
                    deterministic Core validation
```

A unique exact match is the cheapest and safest completion path. Otherwise structured narrowing
may use canonical type, metadata, explicit relationships, caller context, or other cheap
deterministic constraints. This does not freeze a filter API or query language.

The future layered resolver may also accept a stable ID as decisive exact evidence when a caller
already has one. The implemented Phase 9 API deliberately preserves its narrower contract: it
matches only filename-derived primary names and aliases, with optional canonical type filtering.

Semantic/vector candidate retrieval is implemented in Phase 10 for identity expressed through
roles, relationships, contextual
descriptions, paraphrases, and informal names such as `"my wife"`, `"the mother of my children"`,
`"Xavi's wife"`, or `"the other Beatriz"`. A derived index may use stable ID, type, primary name,
aliases, selected metadata, relationships/context, note text, and one local multilingual embedding
per note to return a small likely candidate set. The index is a disposable SQLite file using exact
cosine ranking at current scale. Similarity is never identity confidence. See
[`semantic-retrieval.md`](semantic-retrieval.md) for the implemented contract and benchmark.

The approved Phase 11 architecture direction lets a sufficiently capable contextual reasoner use the
reference, original surrounding context, and only the small candidate set with evidence. For example, in
`"Yesterday we had dinner with Xavi
and the other Beatriz said..."`, candidates may include the user's spouse and a Beatriz recorded as
Xavi's partner. The context may support the latter. If evidence remains insufficient, the result
must remain ambiguous or unresolved.

Phase 11A found that cosine, a Cross-Encoder, and two small local LLMs all produced too many false
resolutions for standalone production use. Later blind strong-reasoner experiments established
feasibility under the tested contract, not proof for every strong LLM or a specific API model. Core
must validate the output schema, ensure a selected ID belongs to the supplied candidate set, and fail
closed on invalid output. The reasoner makes a contextual decision; Core remains authoritative.
Phase 11B.1 benchmarked three OpenAI models without production wiring. The initial zero-shot prompt
selected none. A controlled prompt-parity follow-up reused the ten pre-existing Phase 11A calibration
examples; Sol then passed with zero clear false resolutions and 98.89% frozen-label accuracy after
both cheaper models retained clear false resolutions. A repeat reproduced all 90 outcome/ID
decisions. The human selected Sol with medium reasoning and the frozen ten-example prompt as the
Phase 11 quality baseline; any cost optimization must preserve its measured safety and quality.
Integration, privacy, retention, evidence minimization, and fallback choices remain pending. See
[`ADR 0003`](../decisions/0003-phase-11b1-openai-model-validation.md).

Phase 11B.1c is complete. The accepted resolution direction is exact unique matching resolved
locally, followed otherwise by broad local candidate retrieval, a future safe candidate-reduction
strategy if needed, the strong contextual reasoner, and deterministic Core validation. Cosine is
retrieval evidence only: the tested semantic identity fast path produced 13 clear false resolutions
and is rejected. On the frozen 1,000-note fixture, contextual-only MiniLM reached 72% Recall@5,
80% @20, 88% @50, and 100% @100. This indicates a candidate reduction/ranking problem in this
fixture, not proof of arbitrary real-vault recall. The tested WordNet/OMW hybrid and mMARCO
Cross-Encoder reranker are rejected/deferred; no production retrieval dependency or pipeline change
was adopted. Future candidate reduction and compact retrieval summaries are tracked in GitHub issue
#20. Phase 11B.2 remains the next planned phase: production integration plus privacy/evidence
minimization.

### Resolution before canonical link creation

The planning/LLM layer may identify semantic references, but Odyssey Core must resolve them before
final Markdown persistence. After identity is settled, rendering may produce canonical wikilinks
that preserve the user's wording as link text:

```markdown
[[Beatriz Hidalgo|my wife]]
[[Carrefour Balma|Carrefour]]
```

One occurrence of `"my wife"` or `"Carrefour"` in prose does not automatically add that phrase to
the target note's aliases. Aliases remain meaningful identity synonyms, not a repair mechanism for
arbitrary generated links. Automated persistence should not emit broken wikilinks by default.

### `resolve_exact_entity` — deterministic exact identity decision

- **Purpose:** determine whether an already-extracted reference has zero, one, or several exact
  identity matches.
- **Input:** a `VaultRepository`, parsed canonical schema, query, and optional canonical type.
- **Output:** an `ExactEntityResolution` with all exact candidates and one of `EXACT_MATCH`,
  `NO_EXACT_MATCH`, or `AMBIGUOUS_EXACT_MATCH`; its `candidate` property is populated only for
  `EXACT_MATCH`.
- **Can see:** exact structured candidates containing stable ID, canonical type, primary lookup
  name, vault-relative path, matched stored value, and match kind.
- **Must not know or do:** inspect prose or relationships for identity, interpret a full user
  sentence, use semantic or partial similarity, choose among several exact candidates, conclude
  that an entity is absent after no exact match, create an entity, or write anything.
- **Status:** **PHASE 9 — IMPLEMENTED**.
- **Concrete example:**

  ```python
  resolve_exact_entity(repository, schema, "Carrefour", type="store")
  ```

  With one alias match, the actual result shape is:

  ```python
  ExactEntityResolution(
      outcome=ExactResolutionOutcome.EXACT_MATCH,
      query="Carrefour",
      type="store",
      candidates=(
          ExactEntityCandidate(
              path="stores/Carrefour Balma.md",
              id="store-carrefour-balma",
              type="store",
              primary_name="Carrefour Balma",
              match_kind=MatchKind.ALIAS,
              matched_value="Carrefour",
          ),
      ),
  )
  ```

  Zero candidates produce the same structure with
  `outcome=ExactResolutionOutcome.NO_EXACT_MATCH` and `candidates=()`. This means only that exact
  evidence was absent; it does not mean the entity is absent. Several exact candidates produce
  `ExactResolutionOutcome.AMBIGUOUS_EXACT_MATCH` and retain every candidate. A malformed or
  schema-invalid existing note raises `ExactEntityLookupError` because lookup cannot decide safely.

### `find_exact_entity_candidates` — exact identity-candidate discovery

- **Purpose:** discover explainable exact identity candidates across validated Markdown notes.
- **Input:** a `VaultRepository`, parsed canonical schema, already-extracted entity name, and
  optional canonical type constraint.
- **Output:** an immutable, deterministically ordered tuple of `ExactEntityCandidate` values.
- **Can see:** vault-relative paths, raw Markdown supplied by the repository, parsed `Note` values,
  and the supplied schema. The filename stem is available here as storage context.
- **Must not know or do:** perform general knowledge search, interpret prose or wikilinks, return
  fuzzy or partial matches, rank semantically, modify notes, or move domain behavior into storage.
- **Status:** **PHASE 9 — IMPLEMENTED** as a read-only linear scan.
- **Concrete example:**

  ```python
  find_exact_entity_candidates(repository, schema, "Carrefour", type="store")
  ```

  can return:

  ```python
  (
      ExactEntityCandidate(
          path="stores/Carrefour Balma.md",
          id="store-carrefour-balma",
          type="store",
          primary_name="Carrefour Balma",
          match_kind=MatchKind.ALIAS,
          matched_value="Carrefour",
      ),
  )
  ```

Matching removes surrounding whitespace and applies Unicode `casefold()` only. Primary filename
stem matches sort before alias matches; remaining ordering uses primary name, path, and stable ID.
No punctuation rewriting, stemming, edit distance, phonetics, transliteration, embeddings, or
“only candidate” heuristic participates.

Every listed Markdown note is read, parsed, and validated before results are returned, even when a
type filter would later exclude it. A parse or validation failure raises `ExactEntityLookupError` with
the relative path and preserves the original error as its cause. Silently skipping an invalid note
could produce a false `NO_EXACT_MATCH` and enable a future duplicate.

### Primary lookup name and logical identity

Phase 9 derives `primary_name` from the vault-relative filename stem:

```text
path:          stores/Carrefour Balma.md
primary_name:  Carrefour Balma
stable id:     metadata["id"]
aliases:       metadata.get("aliases", [])
```

This is a small V1 composition choice, not a schema change. `Note` remains path-independent, and
the metadata ID remains stable when a file is renamed. Renaming a file changes its primary lookup
name. If this causes demonstrated failures, a universal canonical name field requires a separate
schema proposal and human approval.

### `VaultRepository.list_markdown_paths` — path discovery

- **Purpose:** list contained regular Markdown files deterministically.
- **Input:** `repository.list_markdown_paths()`.
- **Output:** sorted vault-relative POSIX paths.
- **Can see:** contained filesystem entries and paths only.
- **Must not know or do:** read note content, understand what names mean, or match a query.
- **Status:** **IMPLEMENTED**.
- **Concrete example:**

  ```python
  ["products/Lactel.md", "stores/Carrefour Balma.md"]
  ```

### `VaultRepository.read_text` — raw note read

- **Purpose:** read one contained Markdown file as UTF-8 text.
- **Input:** `repository.read_text("stores/Carrefour Balma.md")`.
- **Output:** raw text unchanged.
- **Can see:** the relative path and raw UTF-8 text.
- **Must not know or do:** parse, validate, infer identity, or interpret Carrefour.
- **Status:** **IMPLEMENTED**.
- **Concrete example output:**

  ```markdown
  ---
  aliases: ["Carrefour"]
  created_at: "2026-08-16T08:00:00Z"
  created_by: "odyssey"
  id: "store-carrefour-balma"
  revision: 1
  schema_version: 1
  type: "store"
  updated_at: "2026-08-16T08:00:00Z"
  updated_by: "odyssey"
  ---

  # Carrefour Balma

  Closes at 21:00.
  ```

### `VaultRepository.create_text` — create-only persistence

- **Purpose:** create one new contained Markdown file without overwriting an existing file.
- **Input:** a safe relative `.md` path and raw text.
- **Output:** `None` on success or a focused storage exception.
- **Can see:** the target path and text bytes.
- **Must not know or do:** infer metadata, create parent trees, update existing notes, or resolve
  identities.
- **Status:** **IMPLEMENTED**.
- **Concrete example:**
  `repository.create_text("products/Lactel.md", markdown)` returns `None` after creating that file.

### `parse_note` — Markdown decoding

- **Purpose:** decode Odyssey's constrained flat frontmatter and preserve the Markdown body.
- **Input:** complete raw Markdown text.
- **Output:** a path-independent generic `Note`; malformed supported syntax raises
  `NoteFormatError`.
- **Can see:** serialization syntax, metadata values, and unchanged body text.
- **Must not know or do:** load the schema, validate ontology meaning, infer a filesystem path, or
  resolve entities.
- **Status:** **IMPLEMENTED**.
- **Concrete example output:**

  ```python
  Note(
      metadata={
          "id": "store-carrefour-balma",
          "type": "store",
          "aliases": ["Carrefour"],
          "created_at": "2026-08-16T08:00:00Z",
          "updated_at": "2026-08-16T08:00:00Z",
          "created_by": "odyssey",
          "updated_by": "odyssey",
          "revision": 1,
          "schema_version": 1,
      },
      content="# Carrefour Balma\n\nCloses at 21:00.\n",
  )
  ```

  No path is present: parsing understands serialization, not storage placement.

### `validate_note` — canonical instance validation

- **Purpose:** prove that one parsed generic note conforms to an explicitly supplied canonical
  schema.
- **Input:** `validate_note(note, schema)`.
- **Output:** `None` on success; `NoteValidationError` for invalid data or an unusable schema.
- **Can see:** structured metadata, uninterpreted body text, and schema definitions.
- **Must not know or do:** read files, infer names, resolve entities, or alter the note.
- **Status:** **IMPLEMENTED**.
- **Concrete example:** the `Note` above and the canonical schema return `None`. This proves schema
  validity; it does not prove that the query `"Carrefour"` matches the note.

### `serialize_note` — Markdown encoding

- **Purpose:** encode a generic note into Odyssey's deterministic constrained Markdown format.
- **Input:** a `Note` containing supported metadata and body text.
- **Output:** a raw Markdown string; unsupported values raise `NoteFormatError`.
- **Can see:** generic metadata and uninterpreted body text.
- **Must not know or do:** validate ontology meaning, choose a path, write a file, or resolve an
  entity.
- **Status:** **IMPLEMENTED**.
- **Concrete example:** `serialize_note(Note(metadata={...}, content="# Lactel\n"))` returns text
  beginning with `---`, deterministic frontmatter, a closing `---`, and `# Lactel`. It does not
  choose `products/Lactel.md` or persist anything.

### `Note` — path-independent representation

- **Purpose:** carry generic structured metadata together with Markdown content.
- **Input:** metadata and a body string supplied by a parser or caller.
- **Output:** a Python value used by codec, validation, and domain composition.
- **Can see:** metadata values and body text only.
- **Must not know or do:** contain a filesystem path or repository, understand user intent, carry
  entity-resolution state, perform I/O, or validate itself globally.
- **Status:** **IMPLEMENTED**.
- **Concrete example:**

  ```python
  Note(metadata={"id": "product-lactel", "type": "product", ...}, content="# Lactel\n")
  ```

### Filesystem and Markdown vault — authoritative persistence

- **Purpose:** retain portable, human-readable personal knowledge.
- **Input:** UTF-8 Markdown written through approved storage or application boundaries.
- **Output:** ordinary files readable by Odyssey, Obsidian, backup tools, and humans.
- **Can see:** directories, filenames, frontmatter text, body text, and wikilinks.
- **Must not know or do:** make domain decisions or depend on a derived index.
- **Status:** **IMPLEMENTED** and the source of truth.
- **Concrete example:** `stores/Carrefour Balma.md` contains canonical frontmatter and ordinary
  Markdown; the filesystem does not know that its alias matched a request.

## End-to-end multi-unit example

The following shows representations at each boundary. All request and knowledge planning is
conceptual and **PLANNED**; Phases 9 and 10 implement exact lookup and semantic candidate retrieval
only.

1. **Arbitrary user input**

   ```text
   What did I pay for Lactel last time?
   Today I bought Lactel milk at Carrefour Balma.
   Carrefour Balma closes at 21:00, and I normally go there on Saturday.
   Lactel is my usual milk.
   ```

2. **`interpret_request` output — conceptual**

   ```text
   RequestPlan
     retrieval:
       - previous Lactel purchase price
     write:
       - today's purchase
       - facts about Carrefour Balma
       - fact about Lactel
   ```

3. **`decompose_knowledge` output — conceptual**

   ```text
   KnowledgePlan
     Store unit:
       reference: {name: "Carrefour Balma", type: "store"}
       facts:
         - closes at 21:00
         - normally visited on Saturday
     Product unit:
       reference: {name: "Lactel", type: "product"}
       facts:
         - usual milk
     Purchase unit:
       references:
         store -> Store unit
         product -> Product unit
       facts:
         - occurred today
   ```

   Repeated store information is grouped. The purchase retains references to the related units
   instead of duplicating all their context.

4. **Independent exact reference resolution — Phase 9**

   ```python
   store_result = resolve_exact_entity(repository, schema, "Carrefour Balma", type="store")
   product_result = resolve_exact_entity(repository, schema, "Lactel", type="product")
   ```

   Only the store and product references require identity resolution; the purchase unit itself is
   not treated as an entity query, and its facts remain purchase knowledge. These read-only scans
   are independent and may be orchestrated in parallel in the future. Each calls
   `find_exact_entity_candidates`, which follows the read direction: list paths, read raw Markdown,
   parse `Note` values, then validate before returning exact evidence. A future `resolve_entity`
   will compose this exact step with later layers when exact evidence is insufficient.

5. **Dependency-sensitive writing — conceptual**

   The store facts are coalesced into one store mutation. The product facts are likewise grouped.
   A purchase write waits until its store and product references have settled. `NO_EXACT_MATCH`
   continues to later planned resolution and never authorizes creation by itself;
   `AMBIGUOUS_EXACT_MATCH` also requires later evidence or clarification. No such write logic exists
   in Phase 10.

6. **Note transformation — implemented infrastructure, future application composition**

   A future domain capability can construct:

   ```python
   Note(
       metadata={
           "id": "store-carrefour-balma",
           "type": "store",
           "aliases": ["Carrefour"],
           "created_at": "2026-08-16T08:00:00Z",
           "updated_at": "2026-08-16T08:00:00Z",
           "created_by": "odyssey",
           "updated_by": "odyssey",
           "revision": 1,
           "schema_version": 1,
       },
       content="# Carrefour Balma\n\nCloses at 21:00.\nUsually visited on Saturday.\n",
   )
   ```

   In the write direction, `validate_note(note, schema)` returns `None`, `serialize_note(note)`
   returns raw Markdown, and `repository.create_text("stores/Carrefour Balma.md", markdown)`
   persists it. Planning decides relationships; `Note` carries metadata and content; serialization
   produces text; the repository sees only the chosen path and that text. `parse_note` is not part
   of this write path.

## Why exact and semantic candidate retrieval remain separate

These capabilities answer different questions:

```text
resolve_exact_entity("Carrefour", type="store")
    -> Which notes have this exact primary name or alias?

resolve_entity("the other Beatriz", context=...)  [PLANNED]
    -> Which entity does this contextual reference identify, if evidence is sufficient?

find_semantic_entity_candidates("the other Beatriz", context=...)
    -> Which small ranked set should a later resolver consider?

search("What stores do I normally use and what do I buy there?")  [FUTURE]
    -> Which knowledge is relevant to this natural-language question?
```

The generic names `resolve_entity` and `search` remain reserved for future hybrid identity
resolution and general knowledge retrieval. Phase 9 owns deterministic exact evidence. Phase 10
owns semantic candidate ranking only; it adds no LLM, graph traversal, note mutation, watcher, or
additional service.

## n8n and the legacy/admin storage path

n8n remains Odyssey's integration boundary for triggers, webhooks, credentials, scheduling,
external-service orchestration, retries, observability, and future human-in-the-loop flows. Its
existing storage primitives remain administrative, reference, and testing tools—not the normal
future application/domain path:

```text
LEGACY / ADMIN n8n STORAGE PATH

    storage_read       [LEGACY-ADMIN]
    storage_write      [LEGACY-ADMIN]
    storage_list       [LEGACY-ADMIN]
          |
          v
    Markdown vault
```

| Capability | Purpose | Input | Output | Can see | Must not know or do | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `storage_read` | Administrative raw note read/parse utility | approved storage path | stored note representation | n8n item and Markdown serialization | become normal domain lookup or resolution | **LEGACY-ADMIN** |
| `storage_write` | Administrative create-only storage utility | approved path and note data | created file outcome | n8n item and storage representation | implement upsert, resolution, or ontology inference | **LEGACY-ADMIN** |
| `storage_list` | Administrative file discovery | configured storage scope | Markdown path list | filesystem identity | parse, search, or resolve entities | **LEGACY-ADMIN** |

## Physical deployment and source-of-truth rule

The current physical mapping is:

```text
Raspberry Pi host             n8n container
/data/odyssey                 /odyssey
  vault/                        vault/
  config/                       config/
  runtime/                      runtime/
```

Markdown under `/data/odyssey` is authoritative and remains readable through Obsidian and ordinary
file tools. Phase 10's semantic SQLite index is derived, disposable, and explicitly rebuildable from
validated Markdown. It belongs under runtime storage rather than the vault, uses a local embedding
model, and remains only ranking evidence for the future hybrid resolver. Phase 9 continues to
perform its independent exact linear scan and does not access the derived store.

Odyssey Core should eventually be the sole normal writer of knowledge notes. High-level domain
tools provide agents with stable intent-level contracts, centralize validation and idempotency, and
allow internal storage mechanics to evolve without exposing low-level call sequences.
