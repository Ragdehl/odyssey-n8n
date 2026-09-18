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

`odyssey-prod prepare FULL_SHA` and `odyssey-prod deploy FULL_SHA` are explicit promotion actions,
not consequences of merging to `main`. `prepare` materializes the exact 40-character commit in the
dedicated `/home/ragdehl/projects/odyssey-prod-release` worktree without touching systemd. The
operator then provisions/verifies the independent PROD environment, and `deploy` rechecks the exact
release, interpreter, environment source, and data boundaries before installing or restarting only
`odyssey-prod-runtime.service`. Mutable refs such as `main`, short SHAs, and tags are rejected.
The deployment fails closed if the commit cannot be resolved, the release target is invalid/dirty,
production/DEV data roots overlap, the environment source is unsafe, or the already-established
`ragdehl` user manager lacks lingering. It records the exact deployed commit only after health
verification. The ordinary human repository may remain dirty or be on another branch and is never
repaired or rewritten by this action.

The Raspberry source path is a shared **bare Git repository** with a human-facing file tree beside
its `.git` directory; it is not a Git-recognized worktree (`git -C /home/ragdehl/projects/odyssey
rev-parse --show-toplevel` therefore fails). The operator uses that bare repository as the object
store and never treats the adjacent human files as runtime source. The service uses the release
worktree for `WorkingDirectory`, runtime code, and schema. PROD dependencies use the separate
`/home/ragdehl/projects/odyssey-prod-venv` environment, which must be provisioned/updated explicitly
from the selected release during the controlled Raspberry migration; changes to the human
checkout's `.venv` cannot affect PROD. The stable rollback operator is installed outside the
release at `/home/ragdehl/.local/libexec/odyssey-prod` and is promoted only after candidate health
verification. The release worktree is not a vault or data store.

Post-merge Raspberry migration (separate controlled operation; not performed by this repository
change):

1. Confirm the merged commit is present in the shared Git object store and inspect its full SHA.
2. Confirm the normal repository's branch, index, staged changes, and working files are preserved;
   do not clean or repair it as part of deployment.
3. Run `odyssey-prod prepare <full-commit-sha>` from the operator context; this does not start or
   restart the service.
4. Provision/update `/home/ragdehl/projects/odyssey-prod-venv` from the prepared release:
   ```text
   python3 -m venv /home/ragdehl/projects/odyssey-prod-venv
   /home/ragdehl/projects/odyssey-prod-venv/bin/python -m pip install \
     -r /home/ragdehl/projects/odyssey-prod-release/requirements-openai.txt \
     -r /home/ragdehl/projects/odyssey-prod-release/requirements-semantic.txt
   ```
5. Verify the independent interpreter from the prepared release with
   `/home/ragdehl/projects/odyssey-prod-venv/bin/python -c 'import odyssey_runtime, openai, fastembed'`.
6. Run `odyssey-prod deploy <full-commit-sha>`. It rechecks the release and environment before
   installing/restarting the service.
7. Verify the release worktree HEAD, recorded `deployed-commit`, systemd unit's release paths,
   private `/healthz`, and `odyssey-prod status` provenance before any user traffic check.
8. If rollback is needed, explicitly prepare the previously recorded full commit, verify/use a
   dependency environment compatible with that release; do not move
   `main` or restore the human checkout. Leave `/data/odyssey`, n8n, and cloudflared untouched.

Human approval is required before this live migration because it restarts the production runtime
and changes the production code target, even though the repository-side mechanism is automated and
fail-closed.
Starting the runtime may refresh derived indexes; it never makes a provider call merely to pass the
health check.

## Reboot readiness evidence

The controlled reboot on 2026-09-18 exposed two separate startup-order races. The Raspberry booted at
11:39:22 CEST. Docker restored the existing `cloudflared` and `n8n` containers at approximately
11:39:42, and the container DNS reconciliation unit ran from 11:39:43 to 11:39:46. cloudflared
received its bounded startup grace and was reported healthy. n8n was running with a resolver matching
the healthy host resolver, but its private `/healthz` was not ready when the guard first assessed it;
the guard therefore emitted `FAILED service=n8n reason=n8n health endpoint is not ready without DNS
evidence`. The same n8n container became healthy shortly afterwards without recreation. This was a
startup timing race, not stale container DNS or a persistent n8n failure.

The same boot also started `odyssey-prod-runtime.service` before Docker had made its configured
`172.18.0.1` bridge address available. Its first bind failed with `OSError: [Errno 99] Cannot assign
requested address`; systemd's existing `Restart=on-failure` later succeeded after Docker networking
settled. `network-online.target` and a running process are therefore not equivalent to Docker-network
or application readiness. The runtime unit must wait, without changing network state, for the
configured bind address to exist before starting the process. The container guard must likewise give
n8n bounded resolver/DNS/private-health readiness time, preserve immediate stale-resolver recovery,
and fail closed without recreation when readiness expires without stale-DNS proof.

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
