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

This is a conceptual capability map, not a mandatory pipeline. Retrieval does not traverse the write
branch, `resolve_entity` does not necessarily lead to an upsert, and a mixed request may use both
branches.

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
                          +----------+----------+
                          |          |          |
                          v          v          v
                       Unit A     Unit B      Unit C
                          |          |          |
                          +----------+----------+
                                     |
                                     v
                              resolve_entity
                                  [PHASE 9]
                                     |
                                     v
                         find_entity_candidates
                                  [PHASE 9]
                                     |
                                     v
                              upsert_entity
                                 [PLANNED]
                                     |
                                     v
                              save_knowledge
                                 [PLANNED]
                                     |
                                     v
                                   Note
                                     |
                          parse / validate / serialize
                                     |
                                     v
                              VaultRepository
                                     |
                                     v
                              Markdown vault
```

The Phase 9 call direction is narrower:

```text
resolve_entity
      |
      v
find_entity_candidates
      |
      +--> VaultRepository.list_markdown_paths
      +--> VaultRepository.read_text
      +--> parse_note
      +--> validate_note
```

`VaultRepository` remains raw filesystem access. It does not parse Markdown, load schema meaning,
discover identity candidates, resolve identities, or make domain decisions.

## Capability contracts

Every conceptual output below is illustrative unless the capability is marked implemented. Phase 9
does not freeze request-plan or knowledge-plan Python APIs or JSON schemas.

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
- **Status:** **PLANNED**. Text, metadata, wikilink, graph, index, or semantic retrieval choices are
  deliberately not selected in Phase 9.
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
    +---- Carrefour unit ---- resolve_entity ----+
    |                                            |
    +---- Lactel unit ------- resolve_entity ----+  PARALLEL OK
    |                                            |
    +---- another entity ---- resolve_entity ----+
```

Dependencies still determine ordering:

```text
resolve Carrefour
      |
      v
create Purchase referring to Carrefour identity
```

Several facts targeting the same logical entity must be coalesced before mutation rather than race
as independent writes. The rule is: parallelize independent work; serialize or coalesce
dependency-sensitive and same-entity mutations. This property does not require or authorize a DAG
engine, scheduler, LangGraph, workflow engine, or parallel execution framework in Phase 9.

### `upsert_entity` — decide reuse, creation, or update

- **Purpose:** eventually reuse, enrich, or create an entity after safe identity resolution.
- **Input:** a structured entity unit plus resolution evidence.
- **Output:** a future validated entity-write outcome.
- **Can see:** grouped entity facts, resolution outcomes, and note-domain contracts.
- **Must not know or do:** reinterpret the full user request, treat `NOT_FOUND` as unconditional
  creation permission, bypass validation, or silently change the canonical schema.
- **Status:** **PLANNED** for Phase 10; Phase 9 performs no create or update behavior.
- **Concrete conceptual example:** `Carrefour` plus a `RESOLVED` candidate may be reused;
  `NOT_FOUND` requires a later create/reuse decision; `AMBIGUOUS` may require agent or human
  clarification. The permanent write-result shape is not defined here.

### `save_knowledge` — persist approved knowledge changes

- **Purpose:** coordinate validated creations, updates, and links from resolved knowledge units.
- **Input:** dependency-aware knowledge work after required identity and upsert decisions.
- **Output:** a future summary of knowledge saved or requiring clarification.
- **Can see:** approved domain outcomes and note-domain contracts.
- **Must not know or do:** manipulate raw files directly, ignore dependencies, or invent ontology
  schema.
- **Status:** **PLANNED**; Phase 9 does not implement its write behavior.
- **Concrete conceptual example:** after store and product identities are settled, save a purchase
  note linking those entities and report the affected notes. Exact contracts remain a future
  architecture decision.

### `resolve_entity` — conservative identity decision

- **Purpose:** determine whether an already-extracted entity reference maps confidently to an
  existing Odyssey entity.
- **Input:** a `VaultRepository`, parsed canonical schema, query, and optional canonical type.
- **Output:** an `EntityResolution` with all exact candidates and one of `RESOLVED`, `NOT_FOUND`, or
  `AMBIGUOUS`; its `candidate` property is populated only for `RESOLVED`.
- **Can see:** exact structured candidates containing stable ID, canonical type, primary lookup
  name, vault-relative path, matched stored value, and match kind.
- **Must not know or do:** interpret a full user sentence, use semantic or partial similarity,
  choose among several exact candidates, create an entity, or write anything.
- **Status:** **PHASE 9 — IMPLEMENTED**.
- **Concrete example:**

  ```python
  resolve_entity(repository, schema, "Carrefour", type="store")
  ```

  With one alias match, the actual result shape is:

  ```python
  EntityResolution(
      outcome=ResolutionOutcome.RESOLVED,
      query="Carrefour",
      type="store",
      candidates=(
          EntityCandidate(
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

  Zero candidates produce the same structure with `outcome=ResolutionOutcome.NOT_FOUND` and
  `candidates=()`. Several exact candidates produce `ResolutionOutcome.AMBIGUOUS` and retain every
  candidate. A malformed or schema-invalid existing note raises `EntitySearchError` because lookup
  cannot decide safely.

### `find_entity_candidates` — exact identity-candidate discovery

- **Purpose:** discover explainable exact identity candidates across validated Markdown notes.
- **Input:** a `VaultRepository`, parsed canonical schema, already-extracted entity name, and
  optional canonical type constraint.
- **Output:** an immutable, deterministically ordered tuple of `EntityCandidate` values.
- **Can see:** vault-relative paths, raw Markdown supplied by the repository, parsed `Note` values,
  and the supplied schema. The filename stem is available here as storage context.
- **Must not know or do:** perform general knowledge search, interpret prose or wikilinks, return
  fuzzy or partial matches, rank semantically, modify notes, or move domain behavior into storage.
- **Status:** **PHASE 9 — IMPLEMENTED** as a read-only linear scan.
- **Concrete example:**

  ```python
  find_entity_candidates(repository, schema, "Carrefour", type="store")
  ```

  can return:

  ```python
  (
      EntityCandidate(
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
type filter would later exclude it. A parse or validation failure raises `EntitySearchError` with
the relative path and preserves the original error as its cause. Silently skipping an invalid note
could produce a false `NOT_FOUND` and enable a future duplicate.

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
conceptual and **PLANNED**; Phase 9 implements identity resolution only.

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

4. **Independent identity resolution — Phase 9**

   ```python
   store_result = resolve_entity(repository, schema, "Carrefour Balma", type="store")
   product_result = resolve_entity(repository, schema, "Lactel", type="product")
   ```

   These read-only scans are independent and may be orchestrated in parallel in the future. Each
   calls `find_entity_candidates`, which lists paths, reads raw Markdown, parses `Note` values, and
   validates them before returning exact evidence.

5. **Dependency-sensitive writing — conceptual**

   The store facts are coalesced into one store mutation. The product facts are likewise grouped.
   A purchase write waits until its store and product references have settled. `NOT_FOUND` needs a
   later create/reuse decision; `AMBIGUOUS` may need clarification. No such write logic exists in
   Phase 9.

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

   `validate_note(note, schema)` returns `None`, `serialize_note(note)` returns raw Markdown, and
   `repository.create_text("stores/Carrefour Balma.md", markdown)` persists it. Planning decides
   relationships; `Note` carries metadata and content; serialization produces text; the repository
   sees only the chosen path and that text.

## Why Phase 9 is not general search

These capabilities answer different questions:

```text
resolve_entity("Carrefour", type="store")
    -> Which existing store has this exact identity reference?

search("What stores do I normally use and what do I buy there?")  [FUTURE]
    -> Which knowledge is relevant to this natural-language question?
```

The generic name `search` is reserved for future knowledge retrieval. It might later use text,
metadata, wikilinks, graph or index retrieval, or semantic/vector techniques if a demonstrated need
justifies them. Phase 9 uses exact primary names, aliases, canonical types, and stable IDs; it adds
no database, vector index, embeddings, LLM calls, graph traversal, or additional service.

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
file tools. A future cache, graph projection, text index, or vector index must address an observed
need and remain rebuildable from Markdown. Phase 9 performs a straightforward linear scan and does
not access a derived store.

Odyssey Core should eventually be the sole normal writer of knowledge notes. High-level domain
tools provide agents with stable intent-level contracts, centralize validation and idempotency, and
allow internal storage mechanics to evolve without exposing low-level call sequences.
