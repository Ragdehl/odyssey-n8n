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

`odyssey-prod deploy` is an explicit promotion action, not a consequence of merging to `main`. It
fails closed unless the fixed production checkout is clean `main`, exactly matches `origin/main`,
has disjoint production/DEV data roots, has the expected environment source structurally, and the
already-established `ragdehl` user manager has lingering enabled. It installs only the production
operator/service artifacts, enables/restarts only `odyssey-prod-runtime.service`, verifies the
private health endpoint, and records the deployed source commit under the rebuildable runtime root.
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
