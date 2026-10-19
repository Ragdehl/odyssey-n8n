# Codex native permissions verified on Raspberry Pi — 19 October 2026

## Security finding

The built-in Codex :read-only sandbox prevents writes but **does not prevent reading the user home or /data**. An OS probe could open (but never read contents of) the Codex authentication file, the DEV directory, and /data. A read-only reviewer is therefore NOT automatically a private or isolated reviewer.

## Verified fix

New scripts/odyssey_codex_permissions.py supplies two explicit Codex native permission profiles: odyssey-scope-read for Generality/Quality/Testing/Performance, and odyssey-scope-edit for the Builder. Both deny the filesystem root by default, permit only the platform's minimal system dependencies, allow access to the dedicated Git worktree and its approved common Git object store, deny environment files, and deny network access. The developer has write access to the worktree; all auditors are read-only.

scripts/odyssey_agent_cycle.py now calls the real native Codex sandbox with the same profile before each model session. It tests OS-level denial of three host-private paths and network sockets, checks allowed Git and AGENTS.md reads, and checks the role's exact write capabilities. Any failure blocks BEFORE launching a model. The subprocess environment is a positive allowlist of nonsecret variables rather than a broad inherited environment. The profile is passed as explicit TOML CLI configuration so local MCP/user configuration remains ignored while Codex's trusted launcher can still use the existing ChatGPT login.

## Real Pi evidence

- Built-in :read-only: three private resources readable, but writes and network denied. No file contents read.
- Native custom read/write profiles: all three private paths inaccessible, sockets unavailable, Git and the workspace readable, workspace writable only for Builder.
- Actual Codex Luna low session using the exact constrained profile: exit 0, model identity verified, final output OK, 9.1 seconds, 10,032 CLI-reported tokens. No user data or app services accessed, ephemeral Git worktree removed.
- Dedicated tests/runtime/test_codex_scoped_permissions.py includes a genuine Codex sandbox/worktree test; supervisor regression proves that an unexpected permission failure prevents model launch. 100 targeted tests PASS.
- Full cross-surface suite: 1,189 Python and 178 JavaScript PASS plus seven subtests.

## Boundaries

The restriction is enforced on commands/tools running through the Codex native sandbox. This is not a new Linux service user, VM or broker for the authenticated Codex **launcher process itself**, and no permissions are implied for hypothetical future MCP extensions. The supervisor ignores local user plugin/MCP configuration and never uses danger-full-access. Existing token, RAM, time, scope, independent specialist and acceptance gates remain required. It does not authorize unattended deployment or product P4 release.

Observations: /tmp/odyssey-native-readonly-fs-proof-20261019.log, /tmp/odyssey-codex-online-scoped-smoke-result-20261019.log, /tmp/odyssey-agent-permission-scope-fullgate-20261019.log. Reports contain only aggregate indicators and token counts, not credentials or private file contents.
