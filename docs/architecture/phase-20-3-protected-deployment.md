# Phase 20.3 — Protected Raspberry/Cloudflare deployment + E2E

Status: **preparation / architecture gate**. No Cloudflare, network, credential, deployment, or real-vault change is authorized by this document.

## Objective

Expose the existing Odyssey Online mobile web surface through a dedicated protected hostname so that one authorized user can use Odyssey from Chrome on Android without exposing the n8n administration surface, provider credentials, the private runtime, or personal knowledge to unauthenticated Internet requests.

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

The product surface remains the existing n8n-hosted Odyssey Online workflows. This phase does not add an application server, frontend framework, database, queue, or second authentication system.

## Acceptance criteria

Phase 20.3 is complete only when retained evidence shows all of the following:

1. `odyssey.ragdehl.com` (or the explicitly approved equivalent product hostname) is a distinct product hostname from the n8n administration hostname.
2. An unauthenticated request to the Odyssey hostname is rejected by Cloudflare Access before n8n, the runtime, any provider, or the vault is reached.
3. The Cloudflare Tunnel ingress for the Odyssey hostname validates the Access application JWT before proxying traffic to n8n (`Protect with Access` / equivalent origin validation).
4. Every alternate public hostname/path that can reach the same Odyssey product webhooks is also covered by Access or an explicit deny rule. In particular, direct product-webhook requests through `n8n.ragdehl.com` must be blocked before the workflow executes.
5. The existing `n8n.ragdehl.com` administration/OAuth/MCP behavior is not broadly placed behind the Odyssey product policy; only the Odyssey product paths are covered there when needed to close the bypass.
6. The browser page and `/api/request` remain same-origin; no permissive CORS or browser-held provider secret is introduced.
7. First public-path E2E evidence uses disposable/non-personal knowledge and demonstrates:
   - protected page load in Chrome on Android;
   - one grounded read response;
   - one deterministic write acknowledgement against disposable data;
   - one clarification/error path;
   - stable `request_id` behavior for an explicit retry if exercised.
8. No unauthenticated probe causes a provider call, Odyssey action, or vault mutation.
9. Real-vault activation remains a separate explicit human-controlled step after the protected disposable-data E2E is clean.
10. Final repository checks, GitHub CI, SonarCloud, and human security review are clean before merge.

## Out of scope

- Luna-first -> Sol production planner routing.
- Multi-user accounts, shared knowledge, roles, groups, or household permissions.
- Native Android/iOS packaging.
- Durable chat history or conversation synchronization.
- A new reverse-proxy/application service solely for Odyssey.
- Moving n8n administration or changing existing OAuth/MCP callback semantics unless a concrete 20.3 blocker requires an explicit separately approved change.
- Automatic real-vault activation.

## Architecture challenge

Result: **PROCEED with the existing Cloudflare Tunnel + Access boundary; do not add application-level authentication infrastructure.**

### Why this is the smallest sufficient design

The existing system already has the correct semantic and execution boundaries:

```text
browser -> n8n product workflow -> private runtime -> Core
```

The missing responsibility is Internet access control, not another application layer. Cloudflare Access can authenticate the browser before the request reaches n8n, while `cloudflared` can validate the Access JWT at the tunnel/origin boundary.

Because the same n8n instance also has an administration hostname, Phase 20.3 must additionally protect or deny the exact Odyssey product webhook paths on that alternate public hostname. Cloudflare Access supports path-scoped applications/policies, so this anti-bypass rule can remain at the edge instead of adding hostname/authentication logic to Odyssey or n8n workflow code.

This keeps authentication outside Odyssey Core, leaves provider credentials server-side, preserves the existing same-origin browser contract, and avoids breaking the already-working private/Tailscale product path.

### Defense in depth

The required public-path security boundary is:

```text
request
  |
  +-- unauthenticated Odyssey hostname
  |      -> Cloudflare Access blocks
  |
  +-- Access token invalid/missing at Odyssey tunnel ingress
  |      -> cloudflared blocks
  |
  +-- direct n8n admin-host request to an Odyssey product path
  |      -> path-scoped Access / explicit deny blocks
  |
  `-- authorized product request
         -> existing validated Odyssey flow
```

An obscure webhook path is not authentication.

## Proposed deployment decisions

These are the intended defaults but the actual security/network mutation still requires explicit human approval:

- Product hostname: `odyssey.ragdehl.com`.
- Access model: one self-hosted Cloudflare Access application, deny by default, with an Allow policy only for the approved user identity.
- Tunnel origin validation: enable Cloudflare Tunnel `Protect with Access` for the Odyssey public-hostname ingress using the Access application audience tag.
- Origin: existing n8n service; do not expose the Python Odyssey runtime publicly.
- Alternate-host anti-bypass: cover the exact Odyssey product webhook/static paths under `n8n.ragdehl.com` with path-scoped Access or an explicit deny policy; do not protect unrelated n8n admin/OAuth/MCP paths.
- n8n administration hostname: remain logically separate and otherwise unchanged by the Odyssey product policy.

## Implementation sequence

### 20.3A — repository/security preparation

Safe/reversible work before security mutation:

- preserve the existing browser/workflow behavior unchanged unless deployment evidence demonstrates a code change is necessary;
- inventory the exact Odyssey product webhook/static paths that must be covered on every public hostname;
- define unauthenticated, alternate-host, authenticated, and rollback checks;
- document the exact deploy/evidence checklist.

### 20.3B — protected Cloudflare route

Requires explicit human approval before execution:

- create/confirm the Odyssey public hostname and tunnel ingress;
- create the Access self-hosted application and one-user Allow policy;
- enable tunnel-side Access JWT validation;
- add path-scoped Access/deny coverage for the same Odyssey product paths on `n8n.ragdehl.com`;
- confirm unauthenticated and alternate-host requests are blocked without downstream execution.

### 20.3C — disposable-data E2E

After protection is proven:

- deploy the current checked-in web/workflow version;
- use disposable data only;
- exercise Android Chrome page load and bounded read/write/clarification behavior;
- inspect n8n/runtime evidence for request correlation and absence of unauthorized provider/action activity.

### 20.3D — real-vault activation gate

Requires separate explicit human approval after the disposable E2E passes. No real personal knowledge is activated merely because the protected route exists.

## Rollback

Rollback must be simpler than activation:

1. disable/remove the Odyssey public hostname route or Access application association;
2. remove only the Odyssey-specific path policy on `n8n.ragdehl.com` if rollback requires it;
3. leave the rest of `n8n.ragdehl.com`, OAuth/MCP, the private runtime, and the real vault unchanged;
4. keep repository code and evidence for review rather than deleting history.

A failed public-path test means the product route stays disabled; it does not justify weakening Access or exposing the runtime directly.

## Open decisions

Only deployment-time values remain open:

- approved Access identity / identity provider;
- confirmation of `odyssey.ragdehl.com` as the final product hostname;
- exact Cloudflare dashboard/API mechanics available on the current account;
- exact production webhook URL prefixes generated by the deployed n8n workflows, to scope the alternate-host path policy without affecting unrelated n8n routes.

None of these require a change to Odyssey's semantic architecture.
