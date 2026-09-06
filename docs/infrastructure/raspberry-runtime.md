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

The host user `ragdehl` and n8n container user `node` use compatible UID/GID ownership so authorized components can work without broad world-writable permissions.

See [Local Storage Boundary](../architecture/storage.md) for semantic authority and file-access rules.

## Codex

Codex is started from `/home/ragdehl/projects/odyssey` so it loads `AGENTS.md`. Development sessions may receive additional approved writable paths such as `/data/odyssey` and `/home/ragdehl/docker/n8n` when the task requires them.

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
