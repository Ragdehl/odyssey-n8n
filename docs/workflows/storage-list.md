# `storage_list`

## Purpose

`storage_list` returns the Markdown note paths currently present under the Odyssey vault. It exposes file identity only: it does not return Markdown content, parse metadata, resolve entities, search, index, or apply ontology behavior.

The live n8n workflow is `Odyssey — storage_list` (`kdjF8Oq5NxK26fwq`).

## Contract

The workflow accepts no public parameters. In particular, callers cannot supply a filesystem path, subtree, glob, filter, or note type.

Success returns one item:

```json
{
  "ok": true,
  "paths": ["inbox.md", "people/carlos.md"]
}
```

`paths` contains only vault-relative POSIX paths ending in `.md`, sorted in deterministic lexical order. An empty vault returns `{ "ok": true, "paths": [] }`.

An unexpected native filesystem failure returns:

```json
{
  "ok": false,
  "error": {
    "code": "LIST_ERROR",
    "message": "Unable to list notes"
  }
}
```

## Workflow

```text
storage_list Input (no parameters)
  → native Read/Write Files from Disk (`/odyssey/vault/**/*.md`)
      ├─ matches → discard binary data → normalize and sort relative paths
      └─ error   → empty match becomes `paths: []`; other failures become `LIST_ERROR`
```

The fixed native selector is internal and cannot be changed by a caller. n8n 2.33.7 has no native metadata-only filesystem-list node; its supported glob reader materializes each matched file before returning file identity. This V1 administrative primitive accepts that internal cost, immediately discards binary data, and never exposes note content. Adding a service, dependency, shell workflow, database, or index solely to avoid that read would add disproportionate complexity.

The native file node resolves every matched file through `N8N_RESTRICT_FILE_ACCESS_TO=/odyssey/vault`. That unchanged runtime boundary blocks paths outside the vault and symlink escapes. The shaping step independently rejects any native identity that is not a contained Markdown path.

## Verification

Run `node --test tests/storage_list_logic.test.js` in the n8n runtime, validate the Workflow SDK representation, and run the `storage_read` and `storage_write` regression tests. Live verification uses only a uniquely named disposable subtree and covers empty behavior, root and nested Markdown paths, non-Markdown exclusion, ordering, relative-only output, and symlink containment. Remove every fixture afterward.

This completes the current low-level n8n storage layer with `storage_read` and `storage_write`. It may remain as a V1 administrative, reference, or testing tool after domain logic moves to Odyssey Core.
