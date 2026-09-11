# Phase 20.3 — Protected Raspberry/Cloudflare deployment + E2E

Status: **20.3B partially complete — 20.3D bounded real-vault activation complete; Cloudflare control-plane work remains blocked**.

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

### 20.3C — disposable protected mobile E2E — complete

Before provider-backed product actions, the running real-vault runtime was stopped and a disposable environment was prepared under:

```text
/tmp/odyssey-20-3c/
  vault/
  runtime/
  state/pending/
```

The disposable vault had its own Git repository/baseline commit because production write history expects the configured vault root to be the Git root. Runtime/index/pending data were isolated from real Odyssey data. The existing local embedding model cache was reused because it contains model assets rather than personal knowledge.

The temporary runtime used the same private host boundary:

```text
ODYSSEY_RUNTIME_HOST=172.18.0.1
ODYSSEY_RUNTIME_PORT=8765
ODYSSEY_VAULT_ROOT=/tmp/odyssey-20-3c/vault
ODYSSEY_RUNTIME_ROOT=/tmp/odyssey-20-3c/runtime
ODYSSEY_PENDING_ROOT=/tmp/odyssey-20-3c/state/pending
```

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

Operational closure was then performed with explicit human authorization:

- `odyssey-phase20-3c-runtime.service` was stopped and verified `inactive`;
- port `8765` was verified free;
- `/tmp/odyssey-20-3c` was removed;
- `/run/user/1000/odyssey-20-3c.env` was removed;
- no real-vault runtime was started during cleanup.

A separate follow-up test exposed a future product requirement:

```text
User: ¿Dónde vive?
Odyssey: no grounded evidence / no inferred referent
```

This is **not** a Phase 20.3 failure. The current browser submits each request independently, so the planner never receives the previous visible turns. The fail-closed result is safe, but natural conversation continuity is missing. The future design is owned by [Future Odyssey help and conversation context](future-help-and-conversation-context.md): context should be retrieved on demand by the same planner flow, not by always hard-coding a fixed number of prior messages into every request.

### 20.3D — real-vault activation gate — pending explicit human authorization

20.3C completion does not authorize reconnecting the protected public product flow to real personal knowledge. At the 20.3C close, no runtime is listening on port `8765` and protected Odyssey Online should not be expected to process requests until 20.3D is explicitly authorized and activated.

20.3D authorization permits only the bounded reconnection of the protected Odyssey product flow to the real runtime/vault and a minimal real-data smoke test. It does not authorize merge, unrelated Cloudflare/n8n/OAuth/MCP changes, or broader production/development restructuring.

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

## 20.3C — disposable E2E deployment reconciliation — 2026-09-11

The disposable runtime remained intentionally active with:

```text
ODYSSEY_VAULT_ROOT=/tmp/odyssey-20-3c/vault
ODYSSEY_RUNTIME_ROOT=/tmp/odyssey-20-3c/runtime
ODYSSEY_PENDING_ROOT=/tmp/odyssey-20-3c/state/pending
```

No real-vault path was connected and no 20.3D activation was performed.

The disposable Nora Vidal WRITE/READ evidence remains request-correlated and clean:

| Evidence | Locator/result |
| --- | --- |
| Vault Git commit | `fa6719e0a3c11950d1a6ad039fa5e246181a67b7` (`odyssey: apply request`) |
| Request correlation | Commit trailer `Odyssey-Request: web-0d098c68-efc6-4c40-bddf-3a2f3515f07a` |
| Created note | `Nora Vidal - c66f0167-6819-404d-a9a8-3c6ce3b06a69.md` |
| Fact locator 0 | `odyssey:fact request=web-0d098c68-efc6-4c40-bddf-3a2f3515f07a ordinal=0` — Trabaja en Airbus. |
| Fact locator 1 | `odyssey:fact request=web-0d098c68-efc6-4c40-bddf-3a2f3515f07a ordinal=1` — Vive en Albi. |
| Working tree | Clean at the disposable vault commit; no pending files were present. |

### Active workflow drift and reconciliation

Before reconciliation, the active product workflow was:

```text
name: Odyssey — Online product boundary
id: hMbt07KRz8HVDOUO
active version: e367aa85-c08b-44df-a8de-748b22df8c91
```

The precise source/deployment delta was confined to `Route bounded product result`.
`workflows/odyssey-online.ts` routes `status=needs_attention` with the allowlisted
`clarification_code=UNRECOGNIZED_REQUEST` to the deterministic clarification response before
retrieval/answer routing. The active deployed node omitted that condition and therefore fell
through to the empty completed response. The webhook path, validation, runtime bridge, route
connections, grounded-answerer branch, answerer model/configuration, and
`Odyssey Phase 20.2B OpenAI Answerer` credential binding otherwise matched the checked-in
workflow. This explains the direct-runtime PASS alongside the n8n product-boundary discrepancy.

The supported n8n deployment mechanism was an atomic `update_workflow` operation against the
existing workflow, followed by `publish_workflow`. This preserved the active workflow ID and
avoided a second active `/api/request` workflow or deletion of inactive duplicates. After
reconciliation the active workflow is:

```text
id: hMbt07KRz8HVDOUO
active version: 7c1df175-e9b2-466d-91c4-fa0f15a0e431
webhook: POST /api/request
```

The existing OpenAI answerer credential binding remained in place; no credential was recreated
or auto-assigned.

### Clarification evidence

The direct runtime request `qzxqzx` already passed with `needs_attention`,
`clarification_code=UNRECOGNIZED_REQUEST`, empty actions, `pending_work.required=false`,
`history.status=NOT_ATTEMPTED`, and unchanged disposable-vault HEAD.

After deployment, local n8n request `request_id=qzxqzx` passed:

```json
{
  "request_id": "qzxqzx",
  "status": "needs_attention",
  "kind": "clarification",
  "message": "No he podido interpretar la solicitud. Reformúlala con más detalle."
}
```

n8n execution `233` confirms the bounded path: the runtime returned the expected clarification,
`Route bounded product result` emitted the deterministic clarification, `Need grounded answer?`
took its direct branch, and the OpenAI answerer node did not execute. The runtime recorded exactly
one provider call, `planner.luna` (`gpt-5.6-luna`, low reasoning); no answerer call was made.
Pending work was skipped and no pending file was created. The disposable vault HEAD remained
`fa6719e0a3c11950d1a6ad039fa5e246181a67b7`.

Provider-free checks also confirmed that the active workflow still contains the WRITE/READ
deterministic routing (`succeeded`/`completed` unit acknowledgement and empty response), the
grounded-answerer branch with its explicit evidence projection, and the answerer credential
binding. The focused deterministic source tests passed under the repository virtual environment.

The protected disposable browser/mobile E2E is complete. Real-vault activation is recorded below as a
separate bounded deployment gate; no real-vault provider-backed WRITE was used as activation evidence.

## 20.3D — bounded production-vault activation — 2026-09-11

The explicitly authorized production bootstrap was completed after a fresh preflight. The configured
production vault is `/data/odyssey/vault`; it was empty before mutation, including no canonical
Markdown, and remains empty after bootstrap. The existing `/data/odyssey/.git` parent directory
was inspected and left untouched: it is not the vault repository.

The vault itself is now the exact local Git repository root:

```text
git -C /data/odyssey/vault rev-parse --show-toplevel
/data/odyssey/vault

git -C /data/odyssey/vault rev-parse HEAD
465773757427597b1f6036e94e670c8dd360d882
```

The SHA is the explicit empty baseline commit `odyssey: initialize empty vault`. The vault Git
working tree is clean (`## main`). Only the two previously identified rebuildable production index
artifacts were reset: `/data/odyssey/runtime/context.sqlite3` and
`/data/odyssey/runtime/semantic.sqlite3`. Their guarded Odyssey index deletion methods verified
the index markers before removal. `/data/odyssey/runtime/phase17e-retrieval/` benchmark results
and the embedding cache were not deleted. The existing `build_runtime_from_environment()` path
then rebuilt both SQLite indexes from the empty canonical vault using the configured local
embedding cache, producing zero indexed notes; no durable `/data/odyssey/state/pending` data was
modified.

Before activation, no Odyssey service or process was active and `127.0.0.1:8765` rejected health
requests. The private runtime was started through the established foreground process boundary under
the transient user unit `odyssey-phase20-3d-runtime.service` (PID 202011), using the existing
runtime environment file. Post-start verification showed the unit `active/running`, a listener only
on `172.18.0.1:8765`, HTTP 200 from `http://172.18.0.1:8765/healthz`, and no listener on
`127.0.0.1:8765`. n8n's unrelated `127.0.0.1:18780` listener was unchanged. No synthetic personal
WRITE or provider-backed request was sent.

Operational learning: a parent `/data/odyssey/.git` directory does not make the vault a Git
repository; exact-root and baseline-commit checks must be performed against `/data/odyssey/vault`
itself. Runtime activation also requires an explicit supervisor/environment launch because the
previous disposable service was gone; the runtime remains private on the Docker bridge address.

The full Phase 20.3 acceptance gate is still open because the previously recorded Cloudflare
control-plane work is blocked. Human merge and the remaining security review remain required.
These requirements are deferred from Phase 20.3 so deployment/security completion does not expand into a new product/model contract during the live activation gate.
