# Odyssey Architecture

## Purpose

Odyssey turns unstructured input into reusable personal knowledge. Markdown files remain
authoritative and human-readable; Python owns note and domain behavior; n8n owns integration and
orchestration. The system adds infrastructure only when an observed requirement cannot be met by
these boundaries.

## Capability hierarchy

This is the normal future application path. A higher layer receives a more meaningful but less
storage-specific representation than the layer below it.

```text
USER / AGENT INTENT
        |
        v
HIGH-LEVEL APPLICATION CAPABILITIES
    save_knowledge       [PLANNED]
    get_context          [PLANNED]
        |
        v
DOMAIN / IDENTITY CAPABILITIES
    upsert_entity        [PLANNED]
    resolve_entity       [PHASE 9]
    search               [PHASE 9]
        |
        v
NOTE INFRASTRUCTURE
    validate_note        [IMPLEMENTED]
    parse_note           [IMPLEMENTED]
    serialize_note       [IMPLEMENTED]
    Note                 [IMPLEMENTED]
        |
        v
STORAGE BOUNDARY
    VaultRepository      [IMPLEMENTED]
        |
   +----+------+
   |    |      |
 read create  list
        |
        v
FILESYSTEM
        |
        v
MARKDOWN VAULT (source of truth)
```

The Phase 9 call direction is deliberately compositional:

```text
VaultRepository.list_markdown_paths + read_text
                    |
                    v
              raw Markdown
                    |
                    v
                parse_note
                    |
                    v
                   Note
                    |
                    v
               validate_note
                    |
                    v
                  search
                    |
                    v
              resolve_entity
```

`VaultRepository` remains raw filesystem access. It does not parse Markdown, load schema meaning,
search, resolve identities, or make domain decisions.

## Capability contracts

### User or agent intent — application input

- **Purpose:** express what the person ultimately wants Odyssey to remember or retrieve.
- **Input:** an unstructured request, for example `"Compré leche Lactel en Carrefour"`.
- **Output:** input to a future high-level application capability.
- **Can see:** the complete user request and conversation context supplied by the interface.
- **Must not know or do:** choose vault paths, parse Markdown, infer repository operations, or call
  storage primitives as if they were domain tools.
- **Status:** **PLANNED** application boundary; ChatGPT is the initial intended interface.

### `save_knowledge` — high-level write intent

- **Purpose:** turn one unstructured knowledge input into validated creations, updates, and links.
- **Input:** a full user statement plus applicable caller context.
- **Output:** a future structured summary of knowledge safely saved or requiring clarification.
- **Can see:** the full semantic request and results from lower domain capabilities.
- **Must not know or do:** manipulate raw files directly or silently invent ontology schema.
- **Status:** **PLANNED** for Phase 12. Phase 9 does not implement any part of its write behavior.

### `get_context` — high-level retrieval intent

- **Purpose:** assemble knowledge relevant to a user or application question.
- **Input:** a higher-level request such as “What supermarkets do I normally use and what do I buy
  there?”
- **Output:** a future context package grounded in Odyssey notes.
- **Can see:** the semantic user question and lower-level lookup results.
- **Must not know or do:** equate semantic relevance with entity identity or mutate notes.
- **Status:** **PLANNED** for Phase 11. Semantic, graph, or vector retrieval is not Phase 9.

### Higher-level interpretation — extracted references

- **Purpose:** identify entity references and facts in an original request before identity lookup.
- **Input:** unstructured text such as `"Compré leche Lactel en Carrefour"`.
- **Output:** structured references such as `name="Carrefour", type="store"` and
  `name="Lactel", type="product"`.
- **Can see:** the original language and any interpretation context supplied by its caller.
- **Must not know or do:** decide that a semantically related note is the same entity, or create a
  note merely because resolution returned no exact match.
- **Status:** **PLANNED**; its final application/API placement is not decided in Phase 9.

### `upsert_entity` — domain write decision

- **Purpose:** eventually reuse, enrich, or create an entity after safe identity resolution.
- **Input:** a structured entity and resolution evidence.
- **Output:** a future validated entity-write outcome.
- **Can see:** entity facts, resolution outcomes, and note-domain contracts.
- **Must not know or do:** treat `NOT_FOUND` as permission to bypass validation or change the
  canonical schema.
- **Status:** **PLANNED** for Phase 10; Phase 9 performs no create or update behavior.

### `resolve_entity` — conservative identity decision

- **Purpose:** determine whether an already-extracted entity reference maps confidently to an
  existing Odyssey entity.
- **Input:** a `VaultRepository`, parsed canonical schema, entity query such as `"Carrefour"`, and
  optional canonical `type="store"` constraint.
- **Output:** `EntityResolution` with `RESOLVED`, `NOT_FOUND`, or `AMBIGUOUS`, plus all exact
  candidates. Its `candidate` convenience property is populated only for `RESOLVED`.
- **Can see:** structured candidates containing stable ID, canonical type, primary lookup name,
  vault-relative path, stored matched value, and match kind.
- **Must not know or do:** interpret the original full user sentence, use semantic similarity,
  resolve a partial match, choose among multiple exact candidates, or write anything.
- **Status:** **PHASE 9 — IMPLEMENTED**.

Normal domain outcomes are data, not runtime failures:

```text
zero exact candidates   -> NOT_FOUND
one exact candidate     -> RESOLVED
multiple exact matches  -> AMBIGUOUS
invalid existing note   -> EntitySearchError (lookup could not decide safely)
```

### `search` — deterministic candidate retrieval

- **Purpose:** retrieve explainable identity candidates from all existing Markdown notes.
- **Input:** a `VaultRepository`, parsed canonical schema, already-extracted entity name, and
  optional canonical type constraint.
- **Output:** an immutable, deterministically ordered tuple of `SearchCandidate` values. Each value
  exposes `path`, `id`, `type`, `primary_name`, `match_kind`, and `matched_value`.
- **Can see:** vault-relative paths, raw Markdown supplied by the repository, parsed `Note` values,
  and the supplied schema. The filename stem is available only here as storage context.
- **Must not know or do:** infer meaning from prose or wikilinks, return fuzzy/partial candidates,
  rank semantically, modify notes, or move schema behavior into `VaultRepository`.
- **Status:** **PHASE 9 — IMPLEMENTED** as a deterministic linear scan.

Matching uses only surrounding-whitespace removal and Unicode-aware `casefold()`. Primary filename
stem matches sort before alias matches; remaining ordering uses primary name, path, and stable ID.
No punctuation rewriting, stemming, edit distance, phonetics, transliteration, embeddings, or
“only candidate” heuristic participates in identity decisions.

Search reads, parses, and validates every listed Markdown note before returning—even when a type
filter would later exclude that note. A parse or validation failure raises `EntitySearchError` with
the vault-relative path and preserves the original `NoteFormatError` or `NoteValidationError` as
its cause. Silently skipping the note could produce a false `NOT_FOUND` and enable a future
duplicate, so failing closed is part of the duplicate-prevention contract. Repository listing and
read failures retain their existing storage exceptions.

### Primary lookup name and logical identity

Phase 9 derives `primary_name` from the vault-relative filename stem:

```text
path:          stores/Carrefour Balma.md
primary_name:  Carrefour Balma
stable id:     metadata["id"]
aliases:       metadata.get("aliases", [])
```

This is a deliberately small V1 composition choice, not a canonical-schema change. `Note` remains
path-independent, and `metadata["id"]` remains the stable logical identity when a file is renamed.
The consequence is explicit: renaming the file changes its primary human-readable lookup name.
Aliases remain alternative identity references. If this limitation causes concrete failures, a
universal canonical `name` field may be proposed as a schema change with human approval; Phase 9
does not add `name`, `title`, or `display_name` silently.

### `validate_note` — canonical instance validation

- **Purpose:** prove that one parsed generic note conforms to an explicitly supplied canonical
  schema.
- **Input:** `Note` plus parsed `config/note-schema.json` data.
- **Output:** `None` on success; `NoteValidationError` for an invalid instance or unusable schema.
- **Can see:** structured metadata, uninterpreted body text, and schema definitions.
- **Must not know or do:** read files, infer a filename/name, resolve entities, inspect revision
  history, or alter the note.
- **Status:** **IMPLEMENTED**.

### `parse_note` — Markdown decoding

- **Purpose:** decode Odyssey’s constrained flat frontmatter and preserve the Markdown body.
- **Input:** complete raw Markdown text.
- **Output:** a path-independent generic `Note`; malformed supported syntax raises
  `NoteFormatError`.
- **Can see:** serialization syntax, metadata scalar/array values, and unchanged body text.
- **Must not know or do:** load the canonical schema, validate note meaning, interpret wikilinks or
  prose, infer filesystem placement, or resolve entities.
- **Status:** **IMPLEMENTED**.

### `serialize_note` — Markdown encoding

- **Purpose:** encode a generic note into Odyssey’s deterministic constrained Markdown format.
- **Input:** a `Note` containing supported metadata values and body text.
- **Output:** canonical Markdown text; unsupported values raise `NoteFormatError`.
- **Can see:** generic note metadata and uninterpreted body text.
- **Must not know or do:** validate canonical ontology meaning, choose a path, write a file, or
  update revisions.
- **Status:** **IMPLEMENTED**.

### `Note` — path-independent note representation

- **Purpose:** carry generic structured metadata together with Markdown content.
- **Input:** a metadata mapping and body string supplied by a parser or caller.
- **Output:** a Python value used by codec, validation, and later domain composition.
- **Can see:** metadata values and body text only.
- **Must not know or do:** contain a vault path, implement one class per note type, perform I/O, or
  validate itself against a global schema.
- **Status:** **IMPLEMENTED**.

### `VaultRepository` — raw storage boundary

- **Purpose:** provide contained filesystem access beneath one configured vault root.
- **Input:** a vault root at construction and safe vault-relative Markdown paths for operations.
- **Output:** raw text, deterministic Markdown path lists, create-only persistence, or focused
  storage exceptions.
- **Can see:** filesystem entries, relative paths, bytes, and UTF-8 text.
- **Must not know or do:** parse Markdown, load schema, model notes, search, resolve entities,
  follow unsafe symlinks, or add domain behavior.
- **Status:** **IMPLEMENTED**.

Its operations have narrower contracts:

| Operation | Purpose | Input | Output | Must not do | Status |
| --- | --- | --- | --- | --- | --- |
| `read_text` | Read one contained note unchanged | vault-relative `.md` path | raw UTF-8 text | parse, validate, interpret | **IMPLEMENTED** |
| `create_text` | Persist a new note without overwrite | relative path and raw text | `None` or storage exception | update, create parent trees, infer metadata | **IMPLEMENTED** |
| `list_markdown_paths` | Discover contained regular Markdown files | no query | sorted relative path list | read content, follow symlinks, search meaning | **IMPLEMENTED** |

### Filesystem and Markdown vault — authoritative persistence

- **Purpose:** retain portable, human-readable personal knowledge.
- **Input:** UTF-8 Markdown written through approved storage/application boundaries.
- **Output:** ordinary files readable by Odyssey, Obsidian, backup tools, and humans.
- **Can see:** directories, filenames, frontmatter text, body text, and wikilinks.
- **Must not know or do:** make domain decisions or become dependent on a derived index.
- **Status:** **IMPLEMENTED** and the source of truth.

## End-to-end representation example

For the input:

```text
Compré leche Lactel en Carrefour
```

the layers transform representations as follows. Planned steps explain the intended boundary; they
are not Phase 9 implementation claims.

1. **User intent (planned application input)**

   Input: the full Spanish sentence. Output: the same unstructured request to a future
   `save_knowledge`/interpretation layer. It can see semantic intent but no vault paths.

2. **Higher-level interpretation (planned)**

   Input: the full sentence. Example output:

   ```text
   entity reference: {name: "Carrefour", type: "store"}
   entity reference: {name: "Lactel", type: "product"}
   fact: purchase of Lactel at Carrefour
   ```

   This is where natural language becomes structured references. Phase 9 does not perform it.

3. **`resolve_entity` (Phase 9)**

   Input for one reference:

   ```python
   resolve_entity(repository, schema, "Carrefour", type="store")
   ```

   It asks only “Does this extracted store identity already exist?” It does not ask what notes are
   broadly relevant to shopping or supermarkets.

4. **`search` (Phase 9)**

   Input: query `"Carrefour"`, canonical type `"store"`. It lists paths and composes repository,
   parser, and validator. Given:

   ```text
   stores/Carrefour Balma.md
     metadata: {id: "store-abc123", type: "store", aliases: ["Carrefour"], ...}
   ```

   output is conceptually:

   ```text
   SearchCandidate(
       path="stores/Carrefour Balma.md",
       id="store-abc123",
       type="store",
       primary_name="Carrefour Balma",
       match_kind=ALIAS,
       matched_value="Carrefour",
   )
   ```

5. **Resolution result (Phase 9)**

   If that is the only exact typed candidate, output is `RESOLVED` with the candidate. Two store
   notes carrying the exact alias produce `AMBIGUOUS`. No exact primary/alias match produces
   `NOT_FOUND`. A filename `Carrefour Balma.md` without alias `Carrefour` does not resolve the
   shorter query.

6. **Future write behavior (planned, not Phase 9)**

   A future `upsert_entity`/`save_knowledge` may reuse `store-abc123`, resolve Lactel separately,
   and save purchase knowledge. Phase 9 stops at identity evidence and performs no creation,
   enrichment, link generation, metadata update, or revision change.

7. **Storage representation (implemented infrastructure)**

   The repository sees only a relative path and raw Markdown. The filesystem sees a Markdown file;
   neither layer knows that `Carrefour` was extracted from a purchase sentence.

## Why Phase 9 is not semantic search

These questions have different evidence requirements:

```text
resolve_entity("Carrefour", type="store")
    -> Which existing store has this exact identity reference?

search("What supermarkets do I normally use and what do I buy there?")
    -> Which knowledge is semantically relevant to this natural-language idea?
```

Only the first is Phase 9. In a vault containing `stores/Carrefour.md`,
`stores/Carrefour Balma.md`, `purchases/Compra Carrefour agosto.md`, and `stores/Auchan.md`, vector
similarity may retrieve related purchase and store documents but cannot establish canonical entity
identity. Exact primary names, aliases, type, and stable IDs are better identity evidence. Vectors
may become useful later for demonstrated semantic retrieval needs, but no database, vector index,
embedding generation, graph traversal, fuzzy library, or additional service is justified here.

## n8n and the legacy/admin storage path

n8n remains Odyssey’s integration boundary for triggers, webhooks, credentials, scheduling,
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
