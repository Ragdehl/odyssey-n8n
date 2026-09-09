# Phase 20.3 — Protected Raspberry/Cloudflare deployment + E2E

Status: **20.3B partially complete — runtime activation complete; Cloudflare control-plane work blocked**.

## Objective

Expose the existing Odyssey Online mobile web surface through a dedicated protected hostname so one authorized user can use Odyssey from Chrome on Android without exposing n8n administration, provider credentials, the private runtime, or personal knowledge to unauthenticated Internet requests.

Target shape:

```text
Chrome Android
    |
    | HTTPS
    v
odyssey.ragdehl.com
    |
    v
Cloudflare Access
    |
    v
cloudflared validates Access JWT
    |
    v
n8n Odyssey Online surface
    |
    v
private runtime -> Odyssey Core
```

The existing n8n product workflows remain the browser-facing application boundary. Do not add an application server, frontend framework, authentication service, database, queue, or permissive CORS layer for this phase.

## Current versioned product surface

The repository currently defines these browser/product contracts:

| Surface | Method | Versioned path/contract |
| --- | --- | --- |
| Browser API | POST | same-origin `/api/request` |
| n8n product trigger | POST | logical webhook path `request` |
| Odyssey page | GET | logical webhook path `odyssey` |
| stylesheet | GET | logical webhook path `styles.css` |
| application JS | GET | logical webhook path `app.js` |
| client JS | GET | logical webhook path `client.js` |

The exact deployed external URL mapping between the browser's `/api/request` contract and the n8n webhook trigger must be inspected on the Raspberry before any Access/path rule is created. Do not infer the active n8n webhook prefix or any Tailscale/Cloudflare rewrite from source alone.

Every public URL that can reach any of these product workflows is part of the security surface. In particular, a dedicated Odyssey hostname is insufficient if the same product webhook remains reachable through `n8n.ragdehl.com` without equivalent Access/deny coverage.

## Acceptance criteria

Phase 20.3 is complete only when retained evidence shows all of the following:

1. `odyssey.ragdehl.com` is a distinct product hostname from the n8n administration hostname.
2. An unauthenticated request to the Odyssey hostname is rejected by Cloudflare Access before n8n, the runtime, a provider, or the vault is reached.
3. The Odyssey tunnel/public-hostname route requires `cloudflared` Access-token validation before proxying L7 traffic to n8n.
4. Every alternate public hostname/path capable of reaching the Odyssey product workflows is covered by Access or an explicit deny rule.
5. `n8n.ragdehl.com` administration, OAuth, MCP, and unrelated webhook behavior are not broadly placed behind the Odyssey product policy.
6. The browser page and `/api/request` remain same-origin; no browser-held provider credential or permissive CORS rule is introduced.
7. Protected disposable-data E2E demonstrates page load, one grounded read, one deterministic write acknowledgement, and one clarification/error path.
8. No unauthenticated probe causes an Odyssey workflow execution, provider call, action, or vault mutation.
9. Real-vault activation remains a separate explicit human-controlled step after protected disposable-data E2E is clean.
10. Repository verification, GitHub CI, SonarCloud, and human security review are clean before merge/activation.

## Architecture challenge

Result: **PROCEED with Cloudflare Tunnel + Access; do not add application-level authentication infrastructure.**

The missing responsibility is Internet access control, not knowledge or application semantics:

```text
browser -> Access -> tunnel -> n8n product workflow -> private runtime -> Core
```

Cloudflare Access can protect a whole hostname or specific application paths. `cloudflared` supports `Protect with Access`, which validates the Access JWT before proxying traffic to the origin. Path-scoped Access rules can therefore close an alternate-host bypass without placing unrelated n8n administration/OAuth/MCP routes behind the Odyssey product policy.

Current Cloudflare references reviewed for this phase:

- https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/
- https://developers.cloudflare.com/tunnel/advanced/origin-parameters/
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/

## Security boundary

```text
request
  |
  +-- unauthenticated Odyssey hostname
  |      -> Cloudflare Access blocks
  |
  +-- missing/invalid Access JWT at protected tunnel route
  |      -> cloudflared blocks
  |
  +-- alternate n8n hostname + Odyssey product path
  |      -> path-scoped Access / explicit deny blocks
  |
  `-- authorized product request
         -> existing n8n -> runtime -> Core flow
```

An obscure hostname or webhook path is not authentication.

## Proposed deployment defaults

These are design defaults only; changing the actual Cloudflare/network configuration still requires explicit human approval.

- Product hostname: `odyssey.ragdehl.com`.
- Access application: self-hosted, deny by default, one approved user identity allowed.
- Tunnel origin validation: `Protect with Access` / equivalent `cloudflared` JWT validation using the application's audience tag.
- Origin: existing n8n service; the Python runtime remains private.
- Alternate-host anti-bypass: cover only the exact Odyssey product URLs on `n8n.ragdehl.com`; preserve unrelated admin/OAuth/MCP paths.
- Browser contract: retain same-origin page + `/api/request`.

## Implementation sequence

### 20.3A — repository and environment inventory

Safe/reversible preparation:

- confirm Phase 20.2G is merged and the Raspberry runtime is actually running the merged Luna/medium contextual default;
- inspect the active n8n webhook URL prefix and the current same-origin mapping for `/api/request`;
- inspect the current Cloudflare Tunnel public-hostname routes without changing them;
- inventory every currently reachable Odyssey Online URL on `n8n.ragdehl.com` and private/Tailscale serving;
- define exact unauthenticated, alternate-host, authenticated, rollback, and no-execution checks;
- preserve the existing browser/workflow implementation unless environment evidence proves a small deployment mapping change is required.

Read-only environment inspection is allowed. Do not mutate Cloudflare, routes, credentials, OAuth, firewall/network settings, or real-vault data during 20.3A.

### 20.3B — protected Cloudflare route

Requires explicit human approval immediately before execution:

- create/confirm `odyssey.ragdehl.com` tunnel route;
- create the Access self-hosted application and one-user Allow policy;
- enable tunnel-side Access JWT validation;
- add the narrow anti-bypass Access/deny coverage on `n8n.ragdehl.com`;
- prove unauthenticated and alternate-host requests are stopped before downstream workflow execution.

### 20.3C — disposable-data E2E

After protection is proven:

- deploy the checked-in Odyssey web/workflow/runtime version as needed;
- use disposable/non-personal data only;
- exercise Android Chrome page load plus bounded read/write/clarification behavior;
- retain request-correlated evidence and confirm no unauthorized provider/action activity.

### 20.3D — real-vault activation gate

Requires separate explicit human approval after disposable E2E passes. A protected route does not itself authorize public-path access to real personal knowledge.

## Rollback

Rollback must be simpler than activation:

1. disable/remove the Odyssey public hostname route or its Access association;
2. remove only Odyssey-specific alternate-host policies if rollback requires it;
3. leave `n8n.ragdehl.com` administration/OAuth/MCP, the private runtime, and real-vault data otherwise unchanged;
4. retain repository/evidence history for review.

A failed public-path check means the Odyssey public route stays disabled; it never justifies weakening Access.

## Open deployment-time values

The remaining environment-backed facts are:

- approved Access identity / identity provider;
- active n8n production webhook prefix and exact `/api/request` mapping;
- current Cloudflare Tunnel ingress/public-hostname configuration;
- exact alternate-host URLs that currently reach Odyssey product workflows;
- whether the current account/dashboard exposes the required Access audience / Protect-with-Access controls exactly as documented.

These are deployment facts, not reasons to change Odyssey Core semantics.

## 20.3A read-only Raspberry inventory

The live Raspberry inspection on 2026-09-09 established the following facts without executing an
Odyssey workflow:

| Component | Observed state |
| --- | --- |
| Odyssey runtime | User transient unit `odyssey-phase20-2f-runtime.service`, PID 162749, listening on `172.18.0.1:8765`; working directory `/home/ragdehl/projects/odyssey` |
| Runtime source timing | The process started at 20:01:16 CEST, before merged Phase 20.2G commit `428ddc6` (21:35:57 CEST). The checked-out source now contains the Luna/medium default, but the running process has not been restarted and therefore must not be represented as having loaded it. |
| n8n | Docker container `n8n`, image `docker.n8n.io/n8nio/n8n:latest`, loopback bind `127.0.0.1:18780 -> 5678`; `N8N_ENDPOINT_WEBHOOK=api` |
| Tailscale | `pi.taild6a0e7.ts.net`; Serve configuration maps `/api` to `http://127.0.0.1:18780/api`. No separate application or origin mapping was present. |
| cloudflared | Docker container `cloudflared`, token-run mode with tunnel ID `0b99a438-fdb8-4978-9035-ef48df039bc4`; control-plane configuration reports only `n8n.ragdehl.com -> http://n8n:5678` plus a `404` catch-all. No local ingress file is mounted. |
| `odyssey.ragdehl.com` | No DNS resolution was returned and no tunnel hostname route was observed. It does not currently exist as an active product hostname. |

The active n8n workflows confirm these production URLs:

```text
https://n8n.ragdehl.com/api/request
https://n8n.ragdehl.com/api/odyssey
https://n8n.ragdehl.com/api/styles.css
https://n8n.ragdehl.com/api/app.js
https://n8n.ragdehl.com/api/client.js
```

The browser's `/api/request` therefore reaches the active `request` webhook through the n8n
`/api` webhook prefix. The private Tailscale path is the same `/api` mapping on
`pi.taild6a0e7.ts.net`; the public Cloudflare tunnel currently routes the whole n8n hostname to
the n8n service, so the Odyssey product paths are alternate public-host bypasses today. The n8n
workflow trigger metadata reports no webhook credentials, and no Access policy is currently
observable at this boundary.

### Read-only attack/bypass inventory

| Host/path | Reaches | Protection requirement |
| --- | --- | --- |
| `odyssey.ragdehl.com/*` | No current route/DNS; future dedicated page, assets, and API | Must be protected before creation |
| `n8n.ragdehl.com/api/request` | Active Odyssey product request workflow -> private runtime | Must receive equivalent Access protection or explicit deny |
| `n8n.ragdehl.com/api/odyssey`, `/api/styles.css`, `/api/app.js`, `/api/client.js` | Active read-only Odyssey page/static workflows | Must receive equivalent protection or explicit deny |
| `pi.taild6a0e7.ts.net/api/*` | Tailscale Serve -> loopback n8n product prefix | Keep private; do not broaden exposure |
| `172.18.0.1:8765` / `127.0.0.1:18780` | Private runtime / n8n origin | Must remain non-public |

No unauthenticated workflow request was sent. The inventory is configuration-derived; it does not
claim an execution or provider reachability test.

### Concrete 20.3B mutation plan and rollback

After a separate human approval immediately before execution, the smallest protected change is:

1. Create `odyssey.ragdehl.com` as a dedicated Cloudflare Tunnel public hostname to the existing
   n8n origin.
2. Create a deny-by-default Cloudflare Access self-hosted application for that hostname with one
   approved user identity and `Protect with Access` / tunnel-side JWT audience validation.
3. Apply equivalent narrow Access/deny coverage to the exact Odyssey product paths on
   `n8n.ragdehl.com` (`/api/request`, `/api/odyssey`, `/api/styles.css`, `/api/app.js`, and
   `/api/client.js`) without placing unrelated n8n administration, OAuth, or MCP routes behind the
   product policy.
4. Prove unauthenticated requests stop before n8n/runtime/provider/vault execution, then run the
   disposable-data E2E gate.

Rollback is to disable/remove only the Odyssey hostname route and its Odyssey-specific alternate-
host policy, leaving n8n administration/OAuth/MCP, the private runtime, and vault data unchanged.
The current routing does not support a safe public Odyssey hostname until these protections are in
place; no Phase 20.3B mutation was performed in 20.3A.

## Recovery evidence — 2026-09-09

The interrupted deployment session was audited before any new deployment write. The result was
**state A**: no Phase 20.3B Cloudflare mutation had occurred. `odyssey.ragdehl.com` still had no
DNS record or tunnel route, and no Odyssey-specific Access application, policy, or alternate-host
protection was present in the observed control-plane state. No public security probe was replayed
while that bypass remained open.

The only authorized recovery mutation was restarting the existing Odyssey runtime. The service is
now active as `odyssey-phase20-2f-runtime.service`, PID `182642`, started at `2026-09-09 22:55:49
CEST`. A provider-free local composition inspection reported:

```text
model=gpt-5.6-luna
reasoning_effort=medium
examples=10
```

The existing n8n container, loopback binding, Tailscale Serve mapping, DNS operating state, and
real-vault boundary were not changed. The runtime token-run process remains connected to the
existing tunnel, but this host exposes no Cloudflare control-plane API credential or management
connector with which to create/read back routes and Access resources. Consequently the protected
hostname, Access policy, tunnel-side JWT validation, alternate-host path protection, and their
unauthenticated probes remain pending; no provider call, Odyssey action, or vault mutation was
caused by recovery.

The exact next authorized operation requires Cloudflare control-plane access for the existing
account/tunnel. It must create only the dedicated hostname and narrow five-path protection, then
read back the non-secret identifiers and run the bounded probes. Do not substitute the tunnel
runtime token, add a broad n8n policy, or run the probes before that protection exists.
