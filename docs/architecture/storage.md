# Local Storage Boundary

## Authority model

Odyssey separates authoritative personal knowledge, durable non-knowledge state, and rebuildable runtime data.

```text
Git repository
  config/note-schema.json   -> authoritative application schema/config

/data/odyssey
  vault/                    -> authoritative personal Markdown
  state/                    -> durable Odyssey app/workflow state
  runtime/                  -> rebuildable indexes/cache/projections
  config/                   -> deployment/runtime config only when explicitly needed
```

The Git repository and personal data are intentionally separate. `/home/ragdehl/projects/odyssey` contains code and documentation; `/data/odyssey` contains persistent personal/operational data and is not committed.

## Host/container mapping

The Raspberry deployment exposes the approved data root to n8n at `/odyssey`:

```text
Raspberry host                 n8n container
/data/odyssey      <------>    /odyssey
  vault/                         vault/
  state/                         state/
  runtime/                       runtime/
  config/                        config/
```

Workflows use container paths; Core/runtime on the host use configured host paths. Deployment paths must not leak into knowledge semantics.

## Canonical vault

`vault/` contains the user's Markdown source of truth. Canonical notes are parsed/validated/mutated through Core contracts; filenames are storage labels, not semantic identity.

`VaultRepository` is the narrow Python filesystem boundary for contained UTF-8 Markdown access. It does not infer ontology, resolve identity, or make domain decisions. Note parsing/serialization and schema validation remain separate layers above it.

Production semantic writes flow through Core materialization/persistence rather than through generic n8n file nodes. This keeps revision, stable-ID, atomic-fact, reference-binding, soft-delete, bulk, and type-migration safety in one authority.

## Durable application state

`state/` holds data that must survive process restarts but is **not personal knowledge** and must not appear in ordinary note scans/embeddings/retrieval.

Phase 17B established `state/pending/` for durable incomplete work. Pending records preserve actionable evidence without becoming Markdown notes or a second knowledge source.

Future durable workflow state should use this boundary only when it cannot be rebuilt and when the semantics are clearly non-canonical.

## Rebuildable runtime state

`runtime/` contains derived state such as SQLite indexes, embeddings/projections, caches, and other artifacts that can be rebuilt from canonical Markdown plus versioned application configuration.

A derived database may improve retrieval or analytics but must never become the only copy of user knowledge.

When a production vault is intentionally bootstrapped/reset and the canonical Markdown state is known, stale derived indexes may be removed and rebuilt from that canonical state. Stop the runtime first, verify the exact configured roots, and delete only artifacts that are explicitly rebuildable; this operation must never be used to infer or replace missing canonical knowledge.

## Git history and production bootstrap

The vault uses local Git history for request-correlated audit/recovery of canonical mutations. Git is not an alternate knowledge model and Git SHAs are not embedded into every fact. `request_id` provides the normal correlation bridge.

Production mutation history has an exact-root invariant:

```text
ODYSSEY_VAULT_ROOT=/data/odyssey/vault
             |
             v
/data/odyssey/vault/.git   <- exact repository root
             |
             v
baseline commit exists before production mutation
```

A Git repository in `/data/odyssey` or another parent directory does **not** satisfy this contract. `GitHistoryRecorder` deliberately rejects a parent repository and also rejects a newly initialized repository with no baseline commit.

Production activation/preflight must therefore verify all of the following before accepting a real write:

1. the configured vault root resolves to the intended production path;
2. `git -C "$ODYSSEY_VAULT_ROOT" rev-parse --show-toplevel` resolves to that exact same path;
3. `git -C "$ODYSSEY_VAULT_ROOT" rev-parse HEAD` succeeds, proving a baseline commit exists;
4. the working tree is in the expected state before the runtime is exposed to product traffic.

Git initialization/bootstrap is an explicit deployment action, never an implicit runtime side effect. An empty production vault may use an explicit empty baseline commit; if personal Markdown already exists, creating its first baseline commits that current content into local history and therefore requires the normal real-data authorization gate.

A stray or incomplete `.git` directory outside the configured vault root must not be mistaken for production history readiness. Check the exact root and HEAD rather than relying on the presence of a `.git` name.

## n8n low-level file utilities

Versioned `workflows/storage-read.ts`, `storage-write.ts`, and `storage-list.ts` preserve early low-level n8n storage utilities. They remain useful for development/reference/administrative scenarios, but they are **not the production semantic write authority**.

Their exact node/error contracts live with the workflow source and tests. Do not create another Markdown contract that can drift from those files; cross-workflow storage semantics belong here.

The native n8n file-node restriction `N8N_RESTRICT_FILE_ACCESS_TO=/odyssey/vault` is the deployment containment boundary for those ordinary vault-file operations. Core pending/runtime access does not implicitly widen native n8n file permissions.

## Permissions and security

The current Raspberry host user and n8n container user use compatible UID/GID ownership so authorized components can access the mounted tree without world-writable permissions.

- Never use broad `777` permissions merely to make a workflow pass.
- Personal vault access and durable state access are separate authorities.
- Path validation and filesystem containment are independent defenses.
- Credentials belong in environment/credential stores, never Markdown docs or the vault.
- Real-vault mutation is a human-controlled deployment/development boundary.

## Synchronization

Cloud/file synchronization (for example OneDrive or another user-selected mechanism) is outside Core semantics. Sync may transport canonical Markdown, but it must not change which copy is authoritative or bypass future conflict/authorization rules.

Fine-grained multi-user confidentiality cannot be implemented by hiding notes in an API after every client already possesses every file. See [Multi-user Collaboration Direction](multi-user-collaboration-direction.md) for that future boundary.

`~/odyssey-data` may be used as a host convenience symlink to `/data/odyssey`; it is not another canonical data location.
