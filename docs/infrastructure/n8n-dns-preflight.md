# Production n8n DNS preflight and stale-resolver recovery

## Purpose

Production n8n can retain Docker resolver state that no longer matches the host after a host DNS handoff. A one-shot successful lookup is not sufficient evidence of health: the Phase 23E incident reproduced intermittent `EAI_AGAIN` inside n8n while host resolution remained healthy.

The reusable invariant is:

```text
host resolver healthy
        +
n8n Node dns.lookup() healthy
        =
provider DNS boundary ready
```

Before publishing or validating a production workflow that may call a provider, run:

```bash
scripts/odyssey-n8n-dns-preflight
```

The preflight is read-only. It does not call the provider API, does not use credentials, does not restart containers, and does not modify DNS/network configuration.

## Result classes

- `dns_preflight=MATCH`: host DNS works and bounded Node `dns.lookup()` calls inside production n8n all succeeded.
- `dns_preflight=DRIFT`: host DNS works but the n8n Node resolver fails. Treat this as container resolver drift until disproven; stop semantic/provider testing.
- `dns_preflight=HOST_UNHEALTHY`: host DNS is not healthy. Do not repair the container first; investigate the host resolver boundary.
- `dns_preflight=UNKNOWN`: n8n is unavailable or its resolver state cannot be established safely.

Recent `EAI_AGAIN` or Docker DNS timeout evidence is reported separately and is diagnostic context, not by itself permission to mutate infrastructure.

For a stronger post-recovery check, increase the bounded probe count without making HTTP calls:

```bash
ODYSSEY_N8N_DNS_PROBES=100 scripts/odyssey-n8n-dns-preflight
```

## Phase 23E observed incident

Two real authenticated SELF requests reached the trusted production path, resolved the real Odyssey user and explicit self binding, completed grounded retrieval, and then failed at the n8n answerer transport boundary with `EAI_AGAIN`. Docker logs correlated both failures with DNS timeouts against an upstream resolver retained by the older n8n container, while the host resolver had no simultaneous failure.

A read-only repeated probe reproduced the split state: host resolution succeeded while Node/libc resolution in n8n failed. Recreating only the existing n8n Compose service, preserving its persistent volume/database, credentials, environment, image and network, refreshed Docker's embedded resolver forwarding. After recreation, host and n8n each passed 100/100 bounded DNS probes with zero `EAI_AGAIN`.

The incident demonstrates that container creation time matters after a host DNS ownership/upstream change. Do not interpret `/etc/resolv.conf` showing `127.0.0.11` as proof that Docker's effective upstream forwarding is current.

## Recovery contract

A `DRIFT` result authorizes no mutation by itself. First establish the exact production Compose project/service and prove persistent storage/configuration ownership. Any recreation remains a separately authorized production action.

When specifically authorized and evidence still supports stale n8n resolver state, the narrow recovery is:

1. verify the exact existing n8n Compose service, image, volume/bind mounts, environment, network and restart policy;
2. recreate **only** n8n with dependencies excluded and no image pull, using the installed Compose semantics (for example `docker compose up -d --no-deps --force-recreate n8n` only when that exact project/file context has been proven);
3. verify the image is unchanged and persistent workflows/credentials/database remain present;
4. verify cloudflared and the Odyssey runtime were not recreated/restarted;
5. run `ODYSSEY_N8N_DNS_PROBES=100 scripts/odyssey-n8n-dns-preflight` and require `MATCH`, 100 successes and zero `EAI_AGAIN` before any semantic/provider test.

Do not substitute a broad Docker restart, Docker daemon DNS change, NetworkManager/Tailscale change, hard-coded public resolver, container recreation of unrelated services, or repeated semantic requests for this targeted recovery.

## Operational rule

For production workflow publication or a live product acceptance test that can invoke the provider:

```text
DNS preflight MATCH
        ↓
publish/validate workflow
        ↓
one bounded semantic acceptance request if authorized
```

If the preflight is `DRIFT`, `HOST_UNHEALTHY`, or `UNKNOWN`, stop before provider/model use and reconcile that boundary first. This keeps DNS/container lifecycle failures separate from Odyssey identity, retrieval, and answer semantics.
