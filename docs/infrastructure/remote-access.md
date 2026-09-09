# Remote Access and Network Exposure

## Purpose

The Raspberry Pi uses separate boundaries for **private administration** and **externally routed web traffic**. No inbound router port forwarding is required.

## Private administration — Tailscale

Tailscale is the normal administrative path to the Raspberry Pi.

```text
Android / admin device
       |
       v
   Tailscale
       |
       v
      SSH
       |
       v
Raspberry / Codex
```

SSH should not be exposed directly to the public Internet. Android currently uses Termius as the SSH client; client choice is not an Odyssey semantic dependency.

### Raspberry DNS ownership

The Raspberry currently keeps Tailscale connectivity while declining Tailscale-managed system DNS:

```text
tailscale --accept-dns=false
```

System DNS is instead owned by NetworkManager. `/etc/resolv.conf` should resolve through NetworkManager's generated resolver file:

```text
/etc/resolv.conf -> /run/NetworkManager/resolv.conf
```

This state was adopted after a Phase 20.3 Codex session lost API connectivity while ordinary Internet-by-IP connectivity still worked. Tailscale had previously generated `/etc/resolv.conf`; after `accept-dns` was disabled, that path remained a regular file with no nameserver entries even though NetworkManager still had a valid DHCP-provided DNS server. The result was successful IP connectivity but failed hostname resolution, including `api.openai.com`.

The recovery was deliberately small and reversible:

1. disable Tailscale DNS management on this Raspberry with `sudo tailscale set --accept-dns=false`;
2. preserve the old `/etc/resolv.conf` as a backup;
3. restore `/etc/resolv.conf` as a symlink to `/run/NetworkManager/resolv.conf`;
4. verify DNS resolution with `getent hosts <hostname>` and HTTPS reachability separately.

Do not edit `/run/NetworkManager/resolv.conf` manually. If Tailscale-managed DNS is re-enabled later, review MagicDNS/global DNS behavior first rather than toggling it during an unrelated Odyssey deployment.

## Cloudflare Tunnel

`cloudflared` runs in Docker and creates an outbound tunnel from the Raspberry to Cloudflare. This allows approved HTTP services such as n8n or the future Odyssey Online hostname to be routed without opening inbound ports on the home router.

```text
Internet
   |
Cloudflare
   |
Cloudflare Tunnel
   |
Raspberry service
```

A tunnel is transport, **not authentication**. An obscure hostname or webhook path is not an access-control boundary.

## Odyssey Online protection

Phase 20.3 requires the user-facing Odyssey Online hostname to have explicit access control before personal-vault or provider-backed actions are exposed through it. The internal Python Odyssey runtime remains non-public; the browser-facing product boundary is n8n.

Cloudflare Access or another explicitly approved mechanism may provide that protection, but choosing/changing the network/security configuration requires human approval and environment-backed E2E verification.

## Security rules

- no public SSH/router port forwarding;
- keep n8n/cloudflared/Tailscale components patched;
- never commit tunnel tokens, OAuth credentials, API keys, or private host details;
- rotate credentials immediately if exposed;
- treat Cloudflare routes/access policies, n8n external exposure, and real-vault activation as explicit security/deployment actions;
- preserve same-origin browser/API behavior where Phase 20 adopts it rather than adding permissive CORS without need.

See [Raspberry Runtime and Development Setup](raspberry-runtime.md) for host/runtime layout and [Phase 20 Odyssey Online MVP](../architecture/phase-20-odyssey-online-mvp.md) for the product boundary.
