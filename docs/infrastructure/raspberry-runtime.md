# Raspberry Runtime and Development Setup

## Purpose

The Raspberry Pi is the current always-on self-hosted environment for n8n, the Odyssey runtime, and Codex-assisted development without requiring a PC to remain powered on.

## Main components

- Debian 13 ARM64;
- Docker / Docker Compose;
- n8n in Docker;
- cloudflared in Docker;
- Codex CLI on the Raspberry Pi;
- n8n MCP access through OAuth;
- Tailscale for private administrative SSH access.

## Important paths

```text
/home/ragdehl/projects/odyssey
  -> Git repository, AGENTS.md, code, docs, tests

/data/odyssey
  vault/    -> authoritative Markdown
  state/    -> durable non-knowledge Odyssey state
  runtime/  -> rebuildable indexes/cache
  config/   -> deployment/runtime config only when needed

/home/ragdehl/docker/n8n
  -> n8n compose/environment configuration
```

The canonical application schema remains in the Git repository at `config/note-schema.json`; `/data/odyssey/config` is not a second schema authority.

## n8n storage mount

Docker maps `/data/odyssey` on the host to `/odyssey` in the n8n container. n8n therefore sees `/odyssey/vault`, `/odyssey/state`, `/odyssey/runtime`, and `/odyssey/config` when its explicit permissions/boundaries allow them.

The host user `ragdehl` and n8n container user `node` both use UID/GID `1000:1000`. `/data/odyssey` and its durable/runtime child directories normally use ownership `1000:1000` and mode `0755` unless a later security review narrows it; do not use `777` to work around permissions.

See [Local Storage Boundary](../architecture/storage.md) for semantic authority and file-access rules.

## Production runtime operator

`odyssey-prod` is the tracked, human-gated production runtime operator. Its persistent user service
is `odyssey-prod-runtime.service`, bound only to the Docker bridge at `172.18.0.1:8765`. It uses
the existing protected environment source at `~/.config/odyssey/secrets.env`; credentials are never
copied into the repository or service file.

`odyssey-prod deploy COMMIT` is an explicit promotion action, not a consequence of merging to
`main`. It resolves the requested commit from the shared Git object store and materializes it in
the dedicated `/home/ragdehl/projects/odyssey-prod-release` worktree. It fails closed if the commit
cannot be resolved, the release target is invalid/dirty, production/DEV data roots overlap, the
environment source is unsafe, or the already-established `ragdehl` user manager lacks lingering.
It installs only the release's production service/operator artifacts, enables/restarts only
`odyssey-prod-runtime.service`, verifies the private health endpoint, and records the exact
deployed commit under the rebuildable runtime root. The ordinary human repository may remain dirty
or be on another branch and is never repaired or rewritten by this action.

The Raspberry source path is a shared **bare Git repository** with a human-facing file tree beside
its `.git` directory; it is not a Git-recognized worktree (`git -C /home/ragdehl/projects/odyssey
rev-parse --show-toplevel` therefore fails). The operator uses that bare repository as the object
store and never treats the adjacent human files as runtime source. The service uses the release
worktree for `WorkingDirectory`, runtime code, and schema. PROD dependencies use the separate
`/home/ragdehl/projects/odyssey-prod-venv` environment, which must be provisioned/updated explicitly
from the selected release during the controlled Raspberry migration; changes to the human
checkout's `.venv` cannot affect PROD. The release worktree is not a vault or data store.

Post-merge Raspberry migration (separate controlled operation; not performed by this repository
change):

1. Confirm the merged commit is present in the shared Git object store and inspect its full SHA.
2. Confirm the normal repository's branch, index, staged changes, and working files are preserved;
   do not clean or repair it as part of deployment.
3. Run `odyssey-prod deploy <full-commit-sha>` from the operator context.
4. Before starting the service, provision `/home/ragdehl/projects/odyssey-prod-venv` from the
   selected release's dependency contract and verify its interpreter/imports independently of the
   human checkout's `.venv`.
5. Verify the release worktree HEAD, recorded `deployed-commit`, systemd unit's release paths,
   private `/healthz`, and `odyssey-prod status` provenance before any user traffic check.
6. If rollback is needed, explicitly deploy the previously recorded full commit and use a
   dependency environment compatible with that release; do not move
   `main` or restore the human checkout. Leave `/data/odyssey`, n8n, and cloudflared untouched.

Human approval is required before this live migration because it restarts the production runtime
and changes the production code target, even though the repository-side mechanism is automated and
fail-closed.
Starting the runtime may refresh derived indexes; it never makes a provider call merely to pass the
health check.

`odyssey-prod status` is read-only. It reports runtime health and source provenance as `MATCH`,
`DRIFT`, or `UNKNOWN`, plus a non-mutating comparison of host DNS reachability with the existing
cloudflared container's resolver/log state. It never restarts n8n or cloudflared; Cloudflare tunnel
recovery remains a separate infrastructure lifecycle and needs separate authorization.

## Codex

The host shell command `odyssey` is the convenience entry point: it changes to `/home/ragdehl/projects/odyssey`, starts Codex from the repository so `AGENTS.md` is loaded, and grants the approved writable paths `/data/odyssey` and `/home/ragdehl/docker/n8n` used by environment-sensitive work.

The n8n MCP connection allows authorized workflow inspection/change/testing under restricted OAuth scopes. Credentials remain in their proper stores and must not be committed.

From Android the normal administrative path is:

```text
Tailscale -> Termius -> SSH -> Raspberry -> odyssey/Codex
```

## Live benchmark calls from Codex

Historical Phase 17E evidence found an environment-specific limitation: direct Raspberry shell calls to `api.openai.com` and the project OpenAI SDK worked, while the same live benchmark calls executed from inside the Codex sandbox failed with `APIConnectionError`.

This is tooling-only and must not block Odyssey development. Focused live model evidence may be run directly from the Raspberry shell while preserving Codex sandbox protections.

If direct Codex outbound access becomes useful later, use the smallest safe change:

- keep sandboxing enabled;
- allow only the minimum provider endpoints required rather than unrestricted Internet access;
- verify with a non-generative SDK smoke call and one bounded benchmark smoke call;
- do not weaken unrelated filesystem, credential, or process protections;
- document only Odyssey-specific configuration that is actually adopted.

## Security

- Codex uses approval-based permissions rather than unrestricted Full Access.
- n8n workflows must be explicitly exposed to MCP.
- Secrets stay in `.env`/credential stores, never documentation or Git.
- Real-vault, network, credential, Cloudflare, and other security-sensitive changes require explicit human approval.
