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

### Manual provider-command environment

The protected Odyssey OpenAI source is `/home/ragdehl/.config/odyssey/secrets.env`. It is also a
systemd `EnvironmentFile=`, so its verified current syntax is `OPENAI_API_KEY=...`, not shell
`export OPENAI_API_KEY=...`. `.bashrc` may source that file, but sourcing a plain assignment alone
does not export it to a manual Python child process. A Codex or shell process started before an
export does not retroactively inherit the variable.

For an explicitly authorized manual provider command, load it in the **same shell** that launches
the child process:

```bash
set -a
. /home/ragdehl/.config/odyssey/secrets.env
set +a
```

Then verify only that the child process has a non-empty key; never print, hash, echo, copy, commit,
or otherwise persist the value. The benchmark runner independently refuses a missing process
environment before reserving evidence or constructing a provider. `/home/ragdehl/docker/n8n/.env`
is the distinct n8n/Cloudflare source, not the Odyssey OpenAI secret source.

## Hot network handoff reconciliation

A live NetworkManager handoff is a known trigger for the production container DNS failure class.
Wi-Fi, DHCP, or resolver changes can update the host resolver while Docker containers retain the
external resolver captured when they were created. On 2026-09-18, the host resolver changed from
`10.235.35.170` to `192.168.1.254`; the existing bounded guard successfully recovered both
production `cloudflared` and n8n in one invocation.

The tracked
`deploy/NetworkManager/dispatcher.d/90-odyssey-container-dns-reconcile` hook is the automatic
trigger design. NetworkManager invokes it for connection-up, DHCP, resolver, connectivity, and
VPN-up events; it asynchronously submits
`systemctl start --no-block odyssey-container-dns-reconcile.service`. The dispatcher performs no
Docker, DNS, or recovery work itself, does not wait for the guard, does not identify a Wi-Fi SSID
or hardcode a resolver, and supports future wired handoffs. Events submit the same fixed-scope
oneshot guard (systemd coalesces starts while it is running, but later events can start another
execution); the guard remains the sole authority and
retains host-DNS validation, production-only scope, one-attempt-per-target recovery, and fail-closed
behavior. Irrelevant NetworkManager events do nothing.

Installation and activation of the dispatcher hook on the Raspberry are separate live operations
requiring human approval after the repository change is merged. The guard's systemd execution bound
is 180 seconds; any caller or operational wrapper must preserve that bound and must not impose a
shorter timeout such as 30 seconds. Partial output or an intermediate observation before the guard
completes is not terminal recovery evidence; verify the per-target terminal result and post-state.

On 2026-09-19, an enabled dispatcher exposed a resolver-transition race during a real Wi-Fi
reactivation. NetworkManager installed IPv4 DNS first, invoked the dispatcher, and installed IPv6
DNS shortly afterwards. The instantaneous host/container mismatch was truthful, but the host set
was incomplete; immediate comparison unnecessarily authorized recreation of both production
containers. A mismatch is therefore actionable only after the guard observes the same normalized,
non-empty host resolver set three times at two-second intervals, confirms its DNS probes, and
rechecks that exact set before each recreation. Eight observations bound resolver sampling to at
most 14 seconds; the two existing five-second DNS probe bounds make the complete stabilization gate
at most 24 seconds inside the existing 165-second guard budget, leaving at least 141 seconds for a
real stale-DNS recovery. Failure to stabilize, malformed or empty evidence, failed DNS probes, or a
later resolver change fails closed with zero further recreation.

The stabilization hardening merged as `abfa4aab1889122f7143e901136ee0a863b55fb1` and was installed
on the Raspberry on 2026-09-19 as the exact source bytes for
`/home/ragdehl/.local/libexec/odyssey-container-dns-reconcile`. A human-authorized healthy-network
execution observed the same normalized IPv4+IPv6 resolver set for three consecutive samples,
reported DNS probes `PASS`, and returned `HEALTHY` for both `cloudflared` and `n8n` with service
result `success`. Post-run evidence confirmed both container IDs/start times were unchanged, the
production runtime remained on the same PID with private `/healthz` HTTP 200, and no `RECOVERING`
path ran. The NetworkManager dispatcher was then re-enabled with mode `0755`; enabling it produced
no immediate guard execution. This closes the temporary `0644` hold described by the earlier
incident notes below.

### September 19 follow-up: hardened guard verification complete

The real handoff left both production containers with stale external resolvers; classification by
that mismatch was correct and both were recreated. The dispatcher-triggered execution at
2026-09-19 01:14:15–01:17:13 CEST nevertheless reported `FAILED` for both post-recreation readiness
checks. The services were subsequently observed healthy without additional recovery being needed
for those readiness symptoms. Generic `FAILED` output did not record which readiness conjunct
failed, so the exact historical per-probe failure cannot be reconstructed. These terminal failures
were not proof of a persistent production outage. A later execution at approximately 05:40 CEST
also reported an n8n mount-fingerprint mismatch; its before/after mount records were not logged.
These observations motivated the parser, fingerprint, diagnostic/readiness, and resolver-stability
hardening. The temporary dispatcher-disable state is no longer current: the merged guard has since
been installed and live-verified as described above.

Repository investigation found three concrete defects/gaps:

- Docker's captured `ExtServers` line separates `host(IPv4)` and `host(IPv6)` with spaces. The old
  comma-only parser greedily combined these into one invalid value. This can falsely classify
  **already-current** DNS as stale and keep both post-recreation readiness predicates false.
  It does not invalidate the genuine earlier stale-DNS handoff; it does invalidate attributing
  every later mismatch/failure to stale DNS or startup timing alone. Parse errors are now unknown
  evidence and fail closed without authorizing recreation.
- The old mount format emitted literal `\n` separators, leaving all mounts on one line. Sorting
  that line did not remove Docker mount-order variation. It also omitted bind sources. This is a
  reproducible false-mismatch mechanism, not proof of the precise cause of the later live mismatch.
- Sequential fixed-attempt readiness windows could expire for a delayed target while the other
  had not yet been recreated. No predicate-level terminal evidence distinguished slow startup,
  resolver parsing, DNS lookup, health response, or registration ordering.

The guard still assesses both targets before recovery and recreates each at most once, sequentially,
with `--no-deps --force-recreate --pull never`. Only the read-only post-recreation waits overlap.
They share a 165-second elapsed-time deadline from guard entry, leaving margin under the unchanged
180-second systemd limit. External Docker/DNS commands are bounded (5 seconds, Compose recreation
45 seconds, HTTP 3 seconds), capped by remaining time; command termination has a one-second kill
grace. Initial startup grace remains bounded and counts toward the same deadline. A slow or hung
dependency may exhaust the budget and fail closed; there is no second recreation or retry loop.
Host DNS is revalidated immediately before each recreation. Callers must still allow the full
180-second service window rather than applying a shorter external timeout.

Terminal diagnostics record normalized expected/observed resolver sets and match/read exit status;
n8n additionally records the DNS-only lookup result/exit status, `/healthz` HTTP status/exit status,
and mount comparison. Cloudflared records the last relevant DNS-error and registration line
positions from the same log snapshot, plus registration readiness. Command exit `124` means the
probe exhausted its command or remaining execution budget, not proof that the service is broken.
No raw tunnel logs, environment, credentials, or response bodies are printed. The correct PROD
private n8n health boundary is `127.0.0.1:18780`; a failed probe at `172.18.0.1:18780` does not prove
n8n is unhealthy. A public unauthenticated Access redirect proves Access interception only, not
authenticated origin health.

The mount fingerprint protects volume identity, bind source, destination, read/write mode,
propagation and the remaining Docker mount metadata. JSON key order, mount order and comma-option
order are normalized; missing optional empty fields are equivalent. Missing mandatory evidence
fails closed. Actual drift logs a bounded diff of normalized mount records (up to 16 lines, 1024
characters per line) and prevents a `RECOVERED` result. A mismatch is evidence to investigate, never
permission to repair mounts, credentials, workflows or data automatically.

The completed 2026-09-19 live re-enable followed this sequence, which remains the rollback-safe
verification pattern for future guard revisions:

1. Keep the dispatcher at `0644`; verify the installed guard/service against the exact merged
   source and `TimeoutStartSec=180`. Install only the approved guard, without promoting runtime or
   frontend assets, changing Compose, or touching DEV/data.
2. Capture current host/container resolver sets, container IDs/start times, normalized n8n mount
   records, runtime PID/health, and private n8n health/readiness. Verify host DNS is healthy.
3. Authorize one healthy-network guard execution with the full 180-second observation window.
   Require `HEALTHY` for both targets and unchanged IDs, mounts and runtime PID. No synthetic event
   or manual rerun should be issued if the result is unexpected.
4. Validate delayed/stale recovery in disposable fixtures first. Any live handoff/recreation test
   needs its own explicit approval, once-per-target evidence, terminal `RECOVERED` results, unchanged
   mount/runtime/workflow boundaries, DNS-only probes and no provider request.
5. Verify the public Access boundary and an authorized non-provider origin check; only after all
   required evidence passes may a separate approved `chmod 0755` re-enable the dispatcher.
   Roll back automatic triggering with `chmod 0644` only; do not restart NetworkManager.

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
