# Raspberry Runtime and Development Setup

## Purpose

Use the Raspberry Pi as an always-on environment for n8n and Codex without requiring a PC to remain powered on.

## Main components

- Debian 13 ARM64
- Docker and Docker Compose
- n8n running in Docker
- cloudflared running in Docker
- Codex CLI installed directly on the Raspberry Pi
- Codex connected to n8n through the n8n MCP server using OAuth
- Tailscale for private remote SSH access

## Important paths

Project and Codex context:

`/home/ragdehl/projects/odyssey`

Contains Git, `AGENTS.md`, documentation and future project code.

Persistent Odyssey data:

`/data/odyssey`

Contains:

- `vault/`
- `config/`
- `runtime/`

n8n Docker configuration:

`/home/ragdehl/docker/n8n`

Contains `compose.yaml` and `.env`.

## n8n storage mount

Docker maps:

`/data/odyssey` on the Raspberry → `/odyssey` inside the n8n container.

Therefore n8n uses paths such as:

- `/odyssey/vault`
- `/odyssey/config`
- `/odyssey/runtime`

while the same files exist on the Raspberry under `/data/odyssey`.

Both the Raspberry user `ragdehl` and the n8n container user `node` use UID/GID `1000:1000`, allowing both to work with these files without broad permissions such as `777`.

## Codex

Codex is started from `/home/ragdehl/projects/odyssey` so that it loads `AGENTS.md`.

Additional writable directories are:

- `/data/odyssey`
- `/home/ragdehl/docker/n8n`

The n8n MCP connection lets Codex read, create, modify, validate and test authorized n8n workflows.

MCP access uses OAuth and restricted scopes. Credentials and n8n Data Tables were not granted.

## Starting the environment

The shell command `odyssey`:

- changes to `/home/ragdehl/projects/odyssey`
- starts Codex
- grants access to `/data/odyssey`
- grants access to `/home/ragdehl/docker/n8n`

From Android the normal workflow is:

Tailscale → Termius → SSH → `odyssey`

## Security

- Codex uses approval-based permissions rather than Full Access.
- n8n workflows must be explicitly exposed to MCP.
- Secrets remain in `.env` or their appropriate credential stores and must not be committed to Git.
