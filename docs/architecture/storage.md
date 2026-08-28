# Local Storage Boundary

## Purpose

Odyssey initially uses Markdown and local files as its source of truth. This keeps personal knowledge readable without Odyssey, directly usable by Obsidian and ordinary file tools, easy to back up, and independent of a database or other service that is not yet needed.

The Git repository and personal data are intentionally separate. `/home/ragdehl/projects/odyssey` contains code and documentation; `/data/odyssey` contains persistent personal and operational data and is not part of the repository.

## Host and container paths

Docker bind-mounts the approved host data directory at a stable path inside n8n:

```text
Raspberry Pi host                n8n container

/data/odyssey        <------>    /odyssey
├── vault/                       ├── vault/
├── config/                      ├── config/
├── state/                       ├── state/
└── runtime/                     └── runtime/
```

The directories have distinct responsibilities:

- `vault/` holds the authoritative Markdown knowledge that Obsidian will eventually use.
- `config/` is reserved for runtime or deployment configuration if a demonstrated need emerges. The canonical application schema is version-controlled in the Git repository at `config/note-schema.json` and is not copied here in Phase 2.
- `state/` holds durable Odyssey application/workflow state that must survive process restarts but is not canonical user knowledge. Phase 17B first uses `state/pending/` for incomplete validated requests. State here is non-rebuildable unless the corresponding workflow explicitly says otherwise.
- `runtime/` holds derived indexes, caches, and other disposable runtime state. Everything here must be rebuildable from the authoritative files and configuration.

Workflows use `/odyssey` and never the Raspberry Pi host path. This storage boundary keeps ontology logic independent of deployment-specific paths and allows the physical storage implementation to change without rewriting ontology workflows.

n8n's native file nodes must be restricted at runtime with `N8N_RESTRICT_FILE_ACCESS_TO=/odyssey/vault`. This is the deployment security boundary for ordinary note-file access: it permits vault reads while rejecting resolved paths under `/odyssey/config`, `/odyssey/state`, `/odyssey/runtime`, other container locations, and symlink escapes from the vault. Workflow path validation remains a separate defense and must accept only safe vault-relative targets. Phase 17B Core pending-state access therefore does not implicitly authorize n8n native file nodes to browse or mutate application state; the Phase 18 integration must expose only the explicit Core boundary it actually needs.

The initial write boundary is deliberately create-only. `storage_write` checks that a target is absent and refuses readable existing notes rather than overwriting them. This simple contract prevents ordinary accidental replacement while leaving revisions and controlled updates to a later explicit primitive. The native existence preflight is not an atomic compare-and-create guarantee, so concurrent creates for the same path are outside the supported contract.

`storage_read`, `storage_write`, and `storage_list` complete the current low-level n8n storage layer. The list primitive uses n8n's fixed native recursive Markdown glob, returns only sorted vault-relative paths, and exposes neither file content nor domain semantics. Because the installed native node materializes matches while enumerating them, this V1 implementation may read files internally before discarding their binary data; avoiding that cost does not justify new infrastructure for an administrative/reference primitive.

Odyssey Core uses a separate, small Python filesystem boundary:

```text
domain/search logic              (later phases)
            |
            v
Note + validation                (Phase 8)
            |
            v
Markdown codec                  (Phase 8)
            |
            v
VaultRepository                  (Phase 7)
            |
            v
filesystem
```

`VaultRepository` receives its vault root when constructed and provides contained UTF-8 reads, exclusive create-only writes, and deterministic recursive Markdown path listing. A read-only root remains usable for listing and reading; create attempts still fail through the normal storage error contract. Paths are literal vault-relative POSIX paths rather than n8n glob selectors. The repository returns and stores raw Markdown text unchanged; it does not parse frontmatter, validate schemas, serialize notes, or apply domain semantics. Parent directories must already exist when creating a note. Its filesystem-containment query lets derived-storage components reject locations inside the authoritative vault without moving semantic behavior into storage.

The Phase 8 Markdown codec is the separate serialization boundary immediately above the repository. It converts constrained YAML-frontmatter Markdown to and from a generic `Note(metadata, content)` without knowing which ontology fields are valid. Canonical note-instance validation is another separate layer above the codec and receives the parsed canonical schema explicitly. The generic note has no filesystem path: metadata such as `id` represents logical identity while vault placement remains a storage concern.

Phase 17B adds a separate, deliberately narrow pending-work repository rooted at `state/pending/`. It stores deterministic JSON workflow evidence and does not reuse `VaultRepository`, the Markdown codec, or the canonical note schema. This separation is intentional: pending work must survive restarts, but it must never appear in ordinary knowledge scans, embeddings, identity resolution, or bulk selection. The pending root is configured explicitly and is not created or populated with real personal state merely by importing Core code or running unit tests.

The source-of-truth distinction is explicit: application schema lives in Git, personal knowledge lives in `/data/odyssey/vault`, durable application/workflow state lives in `/data/odyssey/state`, and rebuildable runtime data lives in `/data/odyssey/runtime`. How n8n obtains the canonical schema or invokes the pending-state boundary will be decided when a workflow needs it; the storage layout does not itself widen native file-node permissions.

`~/odyssey-data` is only a convenience symlink to `/data/odyssey` for interactive host use. It is not a second data location and workflows must not depend on it.

Cloud synchronization, including services such as OneDrive, is external to the Odyssey core. Synchronization policy and tooling will be designed separately so they do not complicate the initial storage contract.

## Permissions

The host user `ragdehl` and the n8n container user `node` both use UID/GID `1000:1000`. The storage root and its durable/runtime child directories should use ownership `1000:1000` and mode `0755` unless a later security review narrows specific state permissions. This lets approved Core/runtime code read the tree and create or update owner-writable files without world-writable permissions or an additional permission mechanism.
