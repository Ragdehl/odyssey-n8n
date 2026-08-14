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
└── runtime/                     └── runtime/
```

The directories have distinct responsibilities:

- `vault/` holds the authoritative Markdown knowledge that Obsidian will eventually use.
- `config/` is reserved for runtime or deployment configuration if a demonstrated need emerges. The canonical application schema is version-controlled in the Git repository at `config/note-schema.json` and is not copied here in Phase 2.
- `runtime/` holds derived indexes, caches, and other disposable runtime state. Everything here must be rebuildable from the authoritative files and configuration.

Workflows use `/odyssey` and never the Raspberry Pi host path. This storage boundary keeps ontology logic independent of deployment-specific paths and allows the physical storage implementation to change without rewriting ontology workflows.

n8n's native file nodes must be restricted at runtime with `N8N_RESTRICT_FILE_ACCESS_TO=/odyssey/vault`. This is the deployment security boundary for note-file access: it permits vault reads while rejecting resolved paths under `/odyssey/config`, `/odyssey/runtime`, other container locations, and symlink escapes from the vault. Workflow path validation remains a separate defense and must accept only safe vault-relative targets.

The initial write boundary is deliberately create-only. `storage_write` checks that a target is absent and refuses readable existing notes rather than overwriting them. This simple contract prevents ordinary accidental replacement while leaving revisions and controlled updates to a later explicit primitive. The native existence preflight is not an atomic compare-and-create guarantee, so concurrent creates for the same path are outside the supported contract.

The source-of-truth distinction is explicit: application schema lives in Git, personal knowledge lives in `/data/odyssey/vault`, and rebuildable runtime data lives in `/data/odyssey/runtime`. How n8n obtains the canonical schema will be decided when a workflow needs it; Phase 2 adds no deployment step or Docker mount.

`~/odyssey-data` is only a convenience symlink to `/data/odyssey` for interactive host use. It is not a second data location and workflows must not depend on it.

Cloud synchronization, including services such as OneDrive, is external to the Odyssey core. Synchronization policy and tooling will be designed separately so they do not complicate the initial storage contract.

## Permissions

The host user `ragdehl` and the n8n container user `node` both use UID/GID `1000:1000`. The storage root and its three directories use ownership `1000:1000` and mode `0755`. This lets n8n read the tree and create or update owner-writable files without world-writable permissions or an additional permission mechanism.
