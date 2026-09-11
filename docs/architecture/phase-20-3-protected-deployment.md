# Phase 20.3 — Protected Raspberry/Cloudflare deployment + E2E

Status: **20.3B complete; 20.3C protected disposable E2E functionally complete pending disposable-runtime shutdown/cleanup; 20.3D real-vault activation not yet authorized**.

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

| Surface | Method | Public product path |
| --- | --- | --- |
| Browser API | POST | `/api/request` |
| Odyssey page | GET | `/api/odyssey` |
| stylesheet | GET | `/api/styles.css` |
| application JS | GET | `/api/app.js` |
| client JS | GET | `/api/client.js` |

Every public URL capable of reaching these workflows is part of the security surface. A dedicated product hostname is insufficient if the same exact product paths remain reachable through `n8n.ragdehl.com` without equivalent protection.

## Acceptance criteria

Phase 20.3 is complete only when retained evidence shows all of the following:

1. `odyssey.ragdehl.com` is a distinct product hostname from the n8n administration hostname.
2. An unauthenticated request to the Odyssey hostname is intercepted by Cloudflare Access before n8n/runtime/provider/vault work.
3. The Odyssey tunnel route requires `cloudflared` Access JWT validation before proxying to n8n.
4. Every alternate public hostname/path capable of reaching Odyssey product workflows is covered by Access or explicit deny behavior.
5. Unrelated `n8n.ragdehl.com` administration/OAuth/MCP behavior remains outside the Odyssey product policy.
6. Browser page/API remain same-origin; no browser-held provider credential or permissive CORS rule is introduced.
7. Protected disposable-data E2E demonstrates page load, one deterministic write acknowledgement, one grounded read, and one fail-closed clarification/error path.
8. No unauthenticated probe causes Odyssey workflow execution, provider call, action, or vault mutation.
9. Real-vault activation remains a separate explicit human-controlled step after disposable-data E2E is clean.
10. Repository verification, CI/review, and human merge/activation gates remain intact.

## Architecture challenge

Result: **PROCEED with Cloudflare Tunnel + Access; do not add application-level authentication infrastructure.**

The missing responsibility is Internet access control, not knowledge semantics:

```text
browser -> Access -> tunnel -> n8n product workflow -> private runtime -> Core
```

The same-origin browser design remains. Cloudflare owns Internet authentication; `cloudflared` validates the Access token at the protected tunnel route; n8n remains integration/orchestration; Core remains semantic authority.

## Security boundary

```text
request
  |
  +-- unauthenticated odyssey.ragdehl.com
  |      -> Cloudflare Access intercepts
  |
  +-- missing/invalid Access JWT at tunnel route
  |      -> cloudflared refuses protected origin forwarding
  |
  +-- n8n.ragdehl.com + exact Odyssey product path
  |      -> dedicated deny-by-default Access application intercepts
  |
  `-- authorized Odyssey request
         -> existing n8n -> runtime -> Core flow
```

An obscure hostname or webhook path is not authentication.

## Implementation sequence

### 20.3A — repository/environment inventory — complete

The read-only inventory established:

- n8n runs in Docker with loopback host bind `127.0.0.1:18780 -> 5678` and `N8N_ENDPOINT_WEBHOOK=api`;
- the runtime listens on Docker-host gateway `172.18.0.1:8765`;
- Tailscale Serve maps `/api` to loopback n8n and remains private;
- the remotely managed Cloudflare tunnel is `raspberry-pi` and originally routed only `n8n.ragdehl.com -> http://n8n:5678` plus a 404 catch-all;
- the public alternate Odyssey paths on `n8n.ragdehl.com` were therefore a real bypass that had to be closed before protected use;
- after the interrupted earlier deployment, the runtime was restarted and provider-free inspection confirmed the running contextual resolver uses Luna/medium with the canonical ten-example calibration prefix.

No unauthenticated workflow execution was used to establish this inventory.

### 20.3B — protected Cloudflare route — complete

The user explicitly authorized the bounded security changes for the existing tunnel/account. A temporary narrow Cloudflare API token was created and stored only on the Raspberry with restrictive filesystem permissions; the secret value was never placed in repository documentation or chat.

The resulting live boundary is:

- dedicated DNS/public hostname `odyssey.ragdehl.com` routed through the existing `raspberry-pi` tunnel;
- self-hosted Cloudflare Access application `Odyssey` for the dedicated hostname;
- one approved user identity with One Time PIN authentication;
- tunnel-side Access JWT validation enabled for the Odyssey ingress route (`required: true`) with the Access application audience/team configuration;
- the original `n8n.ragdehl.com -> http://n8n:5678` tunnel route remains otherwise unchanged;
- a second deny-by-default Access application covers **only** these exact alternate public product paths on `n8n.ragdehl.com`:

```text
/api/request
/api/odyssey
/api/styles.css
/api/app.js
/api/client.js
```

Evidence:

- unauthenticated `odyssey.ragdehl.com/api/odyssey` returns the Cloudflare Access redirect before n8n content;
- all five protected Odyssey paths on `n8n.ragdehl.com` are intercepted by Access;
- `n8n.ragdehl.com/` still returns the normal n8n root, demonstrating that unrelated administration was not broadly wrapped in the Odyssey policy.

### Cloudflared DNS recovery during 20.3B

After successful Access login, the Odyssey route initially returned Cloudflare 502 while local n8n and the public n8n root remained healthy. The existing `cloudflared` container had inherited the host's former Tailscale DNS resolver when the container was created.

Old Docker resolver external server:

```text
100.100.100.100
```

The host had already been intentionally moved back to NetworkManager-owned DNS with Tailscale DNS disabled. Recreating **only** the existing `cloudflared` Compose service caused Docker to inherit the corrected host resolver:

```text
10.47.48.254
```

The 502 disappeared. n8n was not recreated. Current host intent remains:

- Tailscale connected;
- `--accept-dns=false`;
- NetworkManager owns system DNS.

Containers created before a host DNS handoff may retain stale Docker resolver external servers and should be inspected before changing wider network policy.

### Same-origin CSP correction

The Odyssey HTML initially loaded as raw/unstyled content even though the asset endpoints returned the expected files. n8n's webhook response CSP sandbox omitted `allow-same-origin`, causing the page to have an opaque origin and preventing the relative same-origin assets/API from behaving as intended.

Rather than disabling the n8n webhook iframe sandbox globally, a narrowly scoped Cloudflare Response Header Transform Rule was added only for:

```text
host = odyssey.ragdehl.com
path = /api/odyssey
```

It preserves the existing sandbox directives and adds `allow-same-origin`. After deployment, the protected mobile page loaded the intended Odyssey UI and its same-origin CSS/JS correctly. No permissive global CORS or global n8n sandbox disablement was introduced.

### 20.3C — disposable protected mobile E2E — functional gate passed

Before provider-backed product actions, the running real-vault runtime was stopped and a disposable environment was prepared under:

```text
/tmp/odyssey-20-3c/
  vault/
  runtime/
  state/pending/
```

The disposable vault has its own Git repository/baseline commit because production write history expects the configured vault root to be the Git root. Runtime/index/pending data are isolated from real Odyssey data. The existing local embedding model cache is reused because it contains model assets rather than personal knowledge.

The temporary runtime is active on the same private host boundary:

```text
ODYSSEY_RUNTIME_HOST=172.18.0.1
ODYSSEY_RUNTIME_PORT=8765
ODYSSEY_VAULT_ROOT=/tmp/odyssey-20-3c/vault
ODYSSEY_RUNTIME_ROOT=/tmp/odyssey-20-3c/runtime
ODYSSEY_PENDING_ROOT=/tmp/odyssey-20-3c/state/pending
```

Local `/healthz` is healthy and process-environment inspection confirmed the three disposable roots before browser testing.

Protected Android/Chrome evidence:

```text
WRITE
User: Nora Vidal trabaja en Airbus y vive en Albi.
Odyssey: La información se ha guardado.
Result: PASS at product boundary

READ
User: ¿Dónde trabaja Nora Vidal?
Odyssey: Nora Vidal trabaja en Airbus.
Result: PASS; grounded read recovered disposable written knowledge

CLARIFICATION
User: qzxqzx
Odyssey: No he podido interpretar la solicitud. Reformúlala con más detalle.
Product kind: clarification
Result: PASS through protected browser/mobile path
```

The WRITE produced disposable commit `fa6719e0a3c11950d1a6ad039fa5e246181a67b7`, creating only the Nora Vidal note with both facts and request-correlated `Odyssey-Request` / fact locators. The disposable working tree remained clean.

The first protected `qzxqzx` browser attempt incorrectly returned an ordinary empty result. Bounded layer-by-layer diagnosis proved that Luna/Core/runtime were correct: a direct runtime request returned `status=needs_attention`, `clarification_code=UNRECOGNIZED_REQUEST`, no actions, no pending work, no Git history mutation, and unchanged disposable Git HEAD. The same request through local n8n returned an ordinary empty result.

Exporting the deployed n8n workflows then showed the cause: the single active `Odyssey — Online product boundary` workflow (`hMbt07KRz8HVDOUO`) had deployment drift and did not contain the checked-in `needs_attention + UNRECOGNIZED_REQUEST -> kind=clarification` branch present in `workflows/odyssey-online.ts`.

The existing active workflow ID was preserved and reconciled atomically with the version-controlled source, then republished; no second active `/api/request` workflow was created. Focused local verification then returned the expected clarification, with one `planner.luna` provider call, no answerer call, no pending work, and unchanged disposable Git HEAD. The final human-run protected mobile test also returned the dedicated clarification UI, closing the functional 20.3C E2E gate.

Deterministic verification after reconciliation passed: Workflow SDK validation, focused Odyssey Online workflow tests (8 passed), full deterministic suite (694 passed, 79 skipped), Ruff check/format, `git diff --check`, and secret-pattern scan. An initial sandboxed test run had nine runtime-boundary failures solely because the sandbox prohibited the local HTTP fixture; rerunning with the required local fixture allowance passed all 694 runnable tests.

A separate follow-up test exposed a future product requirement:

```text
User: ¿Dónde vive?
Odyssey: no grounded evidence / no inferred referent
```

This is **not** a Phase 20.3 failure. The current browser submits each request independently, so the planner never receives the previous visible turns. The fail-closed result is safe, but natural conversation continuity is missing. The future design is owned by [Future Odyssey help and conversation context](future-help-and-conversation-context.md): context should be retrieved on demand by the same planner flow, not by always hard-coding a fixed number of prior messages into every request.

Remaining 20.3C operational closure:

1. stop the disposable runtime;
2. close/clean disposable test state only after preserving any needed evidence;
3. do **not** reconnect the public product flow to the real vault as part of cleanup;
4. update final PR/roadmap status after shutdown evidence is retained.

### 20.3D — real-vault activation gate — pending

Requires separate explicit human approval after disposable E2E passes. A protected route does not itself authorize public-path access to real personal knowledge.

The disposable runtime must not be silently replaced by a real-vault runtime merely as cleanup from 20.3C. Real-vault connection is the 20.3D decision.

## Rollback

Rollback remains narrower than activation:

1. disable/remove the Odyssey public hostname route or Odyssey Access association;
2. remove only Odyssey-specific exact-path alternate-host policy if required;
3. leave unrelated n8n administration/OAuth/MCP, the private runtime, and real-vault data unchanged;
4. retain repository/evidence history for review.

A failed public-path check means Odyssey public access stays disabled; it never justifies weakening Access.

## Product/deployment follow-up discovered by this phase

The first real mobile interaction demonstrates that a chat-looking UI is not sufficient for conversational semantics. Future work must preserve visible conversations as isolated non-canonical history and let the same Luna-first planner request relevant conversation evidence only when needed. Historical retrieval should eventually support hierarchical conversation/day/week/month/year derived summaries for coarse-to-fine navigation while raw conversation evidence remains authoritative for what was actually said.

The clarification drift incident also established that request diagnostics must include integration/deployment provenance, not only Core/model telemetry. A future advanced inspector should correlate planner/runtime/n8n/final-product outcomes and expose a safe `MATCH | DRIFT | UNKNOWN` view of repository workflow source versus the single active deployed workflow. See [Future Odyssey product usage observability](future-product-usage-observability.md).

These requirements are deferred from Phase 20.3 so deployment/security completion does not expand into a new product/model contract during the live activation gate.
