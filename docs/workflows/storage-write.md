# `storage_write`

## Purpose

`storage_write` creates one Markdown note at a safe vault-relative path from structured metadata and Markdown content. It owns deterministic serialization and never accepts caller-supplied raw frontmatter. The live n8n workflow is `Odyssey — storage_write` (`yIg02EH2IotEHOkS`).

## Contract

Input:

```json
{
  "path": "people/carlos.md",
  "metadata": { "id": "abc", "type": "person", "revision": 1 },
  "content": "# Carlos\n\nText"
}
```

Success returns only the normalized relative path:

```json
{ "ok": true, "path": "people/carlos.md" }
```

Errors use `{ "ok": false, "error": { "code": "...", "message": "..." } }`:

- `INVALID_PATH`: the caller path violates the literal relative POSIX `.md` path contract.
- `INVALID_INPUT`: metadata or content is outside the supported structured serialization subset.
- `ALREADY_EXISTS`: a readable target already exists; `storage_write` does not overwrite it.
- `WRITE_ERROR`: the target cannot be safely checked or written, or another native/runtime write failure occurs.

```text
input
  |
  v
validate path, metadata, and content
  +-- invalid --> INVALID_PATH / INVALID_INPUT
  +-- valid
       |
       v
    target already exists?
       +-- yes --> ALREADY_EXISTS
       +-- cannot determine safely --> WRITE_ERROR
       +-- definitely absent --> serialize and write --> OK / WRITE_ERROR
```

## Flow and responsibilities

```text
Execute Workflow Trigger
  → validate path and structured input
  → deterministically serialize frontmatter
  → native existence preflight
  → native UTF-8 file write
  → shape public result
```

Path normalization and pattern rejection match `storage_read`. The resulting native path is always rooted under `/odyssey/vault`; n8n's `N8N_RESTRICT_FILE_ACCESS_TO=/odyssey/vault` setting remains the deployment boundary that blocks outside-vault paths and symlink escapes.

Metadata must be a non-empty flat object. Keys use `[A-Za-z_][A-Za-z0-9_-]*`; values may be strings, finite numbers, booleans, null, or non-empty flat arrays of those scalar types. Keys are serialized in lexicographic order, strings are always double-quoted JSON/YAML scalars, and arrays use deterministic inline form. Nested values, empty arrays, invalid keys, and non-string content are rejected. Serialization handling deliberately does not validate the canonical ontology schema.

`storage_write` is create-only. It performs a native existence preflight and refuses a readable existing file with `ALREADY_EXISTS`; ambiguous access or filesystem outcomes fail closed as `WRITE_ERROR`. The preflight and write are not an atomic compare-and-create operation, so callers must not issue concurrent creates for the same path. A later controlled update primitive can define revision and overwrite behavior explicitly rather than weakening this contract.

The workflow does not perform entity resolution, search, ontology inference, schema evolution, wikilink extraction, indexing, directory listing, or updates to existing notes.

## Repeatable verification

Run embedded Code-node tests with `node --test tests/storage_write_logic.test.js`, validate the Workflow SDK representation, and run the repository regression suite. Live n8n verification must use a unique disposable fixture path and cover successful creation and exact Markdown state, deterministic metadata order and quoting, repeated-write `ALREADY_EXISTS` behavior without content changes, invalid paths and input, outside-vault/symlink containment, and cleanup of every fixture afterward.

Future creation workflows may call this primitive through its public contract; callers must not depend on the physical vault path or serialization implementation.
