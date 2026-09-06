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
