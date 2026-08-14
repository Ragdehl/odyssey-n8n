# `storage_read`

## Purpose

`storage_read` reads one vault-relative Markdown note and separates its supported frontmatter metadata from its Markdown body. The live n8n workflow is `Odyssey — storage_read` (`4lkNuXTmbqzuO3th`).

## Contract

Input:

```json
{ "path": "people/carlos.md" }
```

Success returns the normalized relative path, parsed `metadata`, and body `content`; it never exposes raw serialization or physical paths:

```json
{
  "ok": true,
  "path": "people/carlos.md",
  "metadata": { "id": "abc", "type": "person" },
  "content": "# Carlos\n\nText"
}
```

Errors use `{ "ok": false, "error": { "code": "...", "message": "..." } }`:

- `INVALID_PATH`: caller input violates the relative POSIX `.md` path contract.
- `NOT_FOUND`: the request path is valid, but no accessible Odyssey note can be obtained. This deliberately does not disclose whether a target is absent, inaccessible, a directory, or blocked through symlink containment.
- `INVALID_NOTE_FORMAT`: a readable note is outside the supported serialization subset.
- `READ_ERROR`: another unexpected native read/runtime failure occurred.

## Flow and responsibilities

```text
Execute Workflow Trigger
  → normalize and validate relative path
  → native Read/Write Files from Disk (read)
  → decode UTF-8 text
  → parse frontmatter and shape public result
```

Path validation accepts only normalized vault-relative POSIX paths ending in `.md`. The native file node depends on the restricted deployment boundary documented in [Local Storage Boundary](../architecture/storage.md); resolved outside-vault paths and symlink escapes are blocked there.

The deterministic parser supports flat top-level keys with strings, quoted strings, booleans, numbers, nulls, flat block arrays, and flat inline arrays. It rejects nested mappings/arrays, multiline scalars, tags, anchors, aliases, inline comments, duplicate keys, and malformed quoting. Parsing is serialization handling only: the workflow does not load or validate against the [canonical note schema](../architecture/note-schema.md).

It does not perform ontology validation, search, entity resolution, wikilink extraction, inference, writes, listing, indexing, or any Phase 4 behavior.

## Repeatable verification

Run the embedded Code-node tests with `node --test tests/storage_read_logic.test.js` and the repository regression suite documented in [Canonical Note Schema](../architecture/note-schema.md). Live n8n verification uses disposable fixtures to cover successful root and nested notes, path normalization/rejection, supported and malformed serialization, schema-independent metadata, missing/directory/denied-symlink `NOT_FOUND` results, outside-vault denial, and symlink containment. Remove every fixture afterward.

Future storage and ontology workflows may call this subworkflow through its public contract; callers must not depend on its physical vault path or parser implementation.
