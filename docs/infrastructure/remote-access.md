# Remote Access and Network Exposure

## Purpose

Provide secure remote access to the Raspberry Pi and expose n8n without opening inbound ports on the home router.

## Tailscale

Tailscale is used for private administrative access.

- Raspberry Pi and Android are connected to the same tailnet.
- Android uses Termius as the SSH client.
- SSH works through Tailscale from Wi-Fi and mobile networks such as 4G/5G.
- No SSH port is exposed publicly on the router.
- Example Tailscale address: `100.64.0.10`.

Typical access path:

Android → Tailscale → SSH → Raspberry Pi → Codex

## Cloudflare Tunnel

Cloudflare Tunnel is used to expose n8n publicly at the illustrative endpoint
`https://n8n.example.com`.

- `cloudflared` runs as a Docker container on the Raspberry Pi.
- The Raspberry initiates an outbound tunnel connection to Cloudflare.
- No inbound port forwarding is required on the router.
- Requests reach Cloudflare first and are forwarded through the existing tunnel to n8n.
- n8n itself is still publicly reachable through its configured URL.

Typical path:

Internet → Cloudflare → Cloudflare Tunnel → n8n

## Why both are used

- **Tailscale:** private access to the Raspberry Pi and SSH.
- **Cloudflare Tunnel:** public web access to n8n without exposing the Raspberry directly through router port forwarding.

## Security notes

- Do not expose SSH directly to the Internet.
- Keep n8n and cloudflared updated.
- Do not store tunnel tokens or other secrets in documentation.
- Rotate a tunnel token immediately if it is exposed.
