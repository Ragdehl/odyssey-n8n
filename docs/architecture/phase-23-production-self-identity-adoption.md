# Phase 23 — production self-identity adoption

Status: **23A repository + live production-boundary inventory complete; 23B trust configuration and trusted-principal projection implemented; 23D reboot-safe production operator deployed and active with MATCH provenance. 23C remains pending its explicit human data/security gate.**

## Objective

Adopt the already-validated Phase 22 self-identity path in production so an authenticated Odyssey
Online request can be projected to an Odyssey-owned stable user ID, bound explicitly to the
existing canonical `person` note for that human, and resolved deterministically for first-person
requests.

Target shape:

```text
Cloudflare Access authentication
        |
        v
cloudflared validates Access JWT
        |
        v
trusted production identity projection
validated (issuer, subject)
        |
        v
IdentityMappingRepository
        |
        v
Odyssey stable_user_id
        |
        +--> authenticated human provenance
        |
        `--> SelfBindingRepository -> canonical person_note_id
                                  |
                                  v
                         deterministic SELF resolution
```

The external principal, Odyssey user, and canonical person note remain three distinct identities.
Provider subject/email values must never become canonical human provenance or note identity.

## 23A — exact production adoption contract

### Repository-backed current state

Phase 22 already provides:

- `ExternalPrincipal` and `IdentityMappingRepository` for durable `(issuer, subject) -> odyssey_user_id` mapping;
- `AuthenticatedActorContext(stable_user_id)` as the only normalized actor shape accepted by the existing execution boundary;
- `SelfBindingRepository` for explicit `odyssey_user_id -> person_note_id` binding;
- authenticated human + application provenance;
- deterministic planner `self_target: "self"` resolution before ordinary semantic identity search;
- fail-closed behavior for missing/invalid actor or binding state;
- successful isolated-DEV SELF READ/WRITE evidence.

The production browser workflow now projects only `iss` and `sub` from the validated Access assertion
as `external_principal`; the private runtime resolves that principal through an existing-only mapping
before constructing `AuthenticatedActorContext`. DEV rendering continues to inject its synthetic actor
from `ODYSSEY_DEV_STABLE_USER_ID`. `IdentityMappingRepository` remains runtime/Core-owned durable state.

The protected production route already has the intended outer trust boundary:

```text
odyssey.ragdehl.com
  -> Cloudflare Access
  -> cloudflared Access JWT validation
  -> n8n product workflow
  -> private Odyssey runtime
```

Phase 23 must reuse this boundary rather than introduce a second authentication service.

### Acceptance criteria

Phase 23 production adoption is complete only when retained evidence shows all of the following:

1. The request identity originates from the already-validated Cloudflare Access principal, never
   from browser-controlled request JSON or untrusted client identity headers.
2. The trusted projection uses an issuer-scoped opaque subject and does not use email/display name
   as the durable identity key.
3. The external principal resolves through `IdentityMappingRepository` to an Odyssey-owned UUID;
   raw provider identity does not enter canonical note provenance.
4. One explicit production self binding maps that Odyssey user ID to the already-existing active
   canonical `person` note by stable note ID. No new person is inferred or created for binding.
5. SELF READ resolves only through that binding; name/similarity fallback cannot replace it.
6. SELF WRITE, if separately authorized for production verification, updates the bound note and
   records the Odyssey user ID as `updated_by.human` while preserving the application actor.
7. Browser input cannot choose or override `stable_user_id`, provider subject, or person note ID.
8. Missing/malformed principal mapping or self binding fails closed and cannot fall through to
   CREATE.
9. Production deployment is an explicit clean-`main` action that records deployed source identity,
   updates only required production components, verifies health/provenance, and fails closed on
   drift or ambiguous targets. The production runtime must be managed through a reboot-safe,
   reproducible operator/service contract rather than a one-off transient unit whose launch state
   disappears after host reboot.
10. The production operator exposes enough status/health evidence to distinguish source drift,
    runtime absence, workflow drift, and tunnel reachability without requiring a semantic/provider
    request. Infrastructure checks should detect known stale-container DNS conditions before
    broader network changes are considered.
11. No production personal-data or security mutation occurs before its explicit human gate.

### Out of scope

- New authentication providers or a custom authentication service.
- Multi-user authorization, shared-note ACLs, or synchronization.
- Email as a durable account identifier.
- New note types, `is_me` flags, first-person aliases, or copied profile facts.
- A new database/service for identity.
- Replacing Cloudflare Access, the existing tunnel, n8n, or the private runtime.
- Conversation persistence/history work.
- Any production write used merely to prove infrastructure when a read-only proof is sufficient.

### Retained 23B trust evidence and implementation

The completed read-only live inventory established, without printing secret/token values:

1. The dedicated `odyssey.ragdehl.com` route has Access required and team configuration, and its
   effective `audTag` is a single entry matching the existing Odyssey Access application audience.
   An earlier apparent missing value was an `EARLIER_SCHEMA_INTERPRETATION_ERROR`: the API returns
   `audTag` as a list, not a scalar string.
2. All five documented Odyssey product paths on `n8n.ragdehl.com` are covered by the narrow Access
   application, while the n8n root remains outside that product-path policy. No Cloudflare repair was
   performed.
3. The production runtime is healthy on `172.18.0.1:8765`, its deployed source provenance is `MATCH`,
   and the reboot-safe service is active and enabled.
4. Pre-PR trust-boundary review found that the historical Tailscale Serve `/api` mapping still reached
   the same production n8n product surface without crossing cloudflared Access validation. That made
   the Access assertion header name insufficient by itself to prove provenance. With explicit human
   authorization, the obsolete Tailscale product Serve mapping was retired. Post-change checks showed
   Serve empty, Tailscale still connected, `accept-dns=false` preserved, SSH administration preserved,
   Funnel disabled, and cloudflared, n8n, and the Odyssey runtime unchanged. No alternate known
   non-cloudflared remote/private ingress remained for `/api/request`; the resulting classification was
   `TRUST_BOUNDARY_SOUND`.

The removal operation used `tailscale serve off`, which was broader than the requested narrow-path
procedure and therefore must not be treated as a reusable path-removal recipe. It was safe in this
specific live state only because post-change evidence established that the obsolete `/api` mapping was
the sole Serve configuration and no unrelated handler was lost. Future Serve changes must inspect the
full live Serve configuration first and must not use a broad disable operation as a substitute for a
narrow removal when unrelated handlers exist or their absence has not been established.

### Operational lessons retained from 23B

- Prefer provider documentation plus effective configuration evidence over inspecting a real user's
  token when that is sufficient to establish the trust contract. Sensitive runtime evidence should be
  the last resort, not the first diagnostic path.
- Reconcile API schema/representation before declaring configuration drift. The false missing-`audTag`
  diagnosis came from treating a list-valued field as though it were a scalar. If a mutation preflight
  contradicts the prior diagnosis, abort the mutation and reconcile the live representation first.
- A trusted header name does not prove trusted provenance. Before making a forwarded identity header
  authoritative, enumerate every ingress that can reach the same workflow and prove that each relevant
  ingress crosses the validation boundary or cannot supply identity-bearing traffic.
- Express live security/network changes as an exact semantic diff and verify the installed CLI/API
  behavior before execution. Broad commands such as `off` or `reset` are not acceptable substitutes
  for a narrow change unless the complete live scope has already been proven to contain only the
  authorized target and the authorization explicitly covers that broader effect.
- If an approval layer reports a denial while the transcript later appears to show a command as run,
  treat live state as `UNKNOWN`. Stop further mutation and verify the actual post-state rather than
  inferring what happened from the transcript alone.
- Separate read-only investigation from mutation authorization. Evidence collection can refine or
  invalidate the premise of a planned change; authorization for one exact mutation must not be reused
  automatically after that premise changes.

The implementation adds a strict runtime `external_principal` shape. PROD n8n extracts only the
issuer and subject claims from the already-validated `Cf-Access-Jwt-Assertion`; it never forwards the
JWT, audience, expiry, email, headers, or browser identity fields. Ordinary traffic uses
`IdentityMappingRepository.resolve_existing`; unknown or malformed mappings fail closed without
creating state. The real production mapping and self binding remain Phase 23C human-gated.

## Architecture challenge

Result: **PROCEED.**

The real problem is trusted identity projection and controlled production promotion, not new
knowledge semantics or new authentication infrastructure. Phase 22 already owns mapping, binding,
provenance, and deterministic SELF behavior; Cloudflare/cloudflared already own Internet
authentication and token validation. Phase 23 should connect those existing boundaries with the
smallest trusted adapter and an explicit production deployment operator.

Do not hard-code one production `stable_user_id` into the browser workflow merely because the
current Access policy has one user. That would make policy membership an implicit identity mapping
and could silently impersonate a newly allowed Access user later. The production request must be
projected from the validated principal on each request.

Do not move `identity-mappings.json` ownership into n8n. Core owns the durable identity mapping
contract. The live inventory confirms the validated principal boundary, so the smallest integration
is an n8n projection followed by the private runtime adapter into that existing Core boundary. No
additional service is justified. The trusted production product ingress is the Cloudflare
Access/cloudflared path; Tailscale remains an administrative SSH boundary rather than an alternate
Odyssey product ingress.

## Production operator requirement discovered during adoption

The Phase 23 live inspection found that the previously working production runtime had been launched
as a transient user unit and was no longer present after a Raspberry reboot. The current production
contract can be reconstructed safely from stable configuration, but the former one-off transient
launch metadata itself was volatile. This is operational debt, not a self-identity semantic failure.

The reboot-safe `odyssey-prod` operator/service is now deployed in production and remains human-gated
for future promotion:

```text
approved clean main
      |
      v
odyssey-prod deploy
      +--> install/update reboot-safe runtime service contract
      +--> preserve canonical /data/odyssey data boundaries
      +--> install only production runtime/operator artifacts
      +--> record exact deployed source identity
      +--> verify private runtime health/provenance plus tunnel diagnostics
      `--> fail closed on drift, ambiguity, or unhealthy dependencies
```

This is not automatic merge-to-PROD promotion. The automation is inside the explicit operator; the
human production gate remains. n8n workflow provenance remains a read-only verification concern and
is outside the runtime service lifecycle.

## Planned sequence after 23A

```text
23A  repository + read-only live boundary inventory                    ✅ complete
23B  trusted validated-principal -> Odyssey-user projection            implementation complete; trust boundary sound; mapping/binding remain gated
23C  explicit real-user -> existing person binding                     pending human data gate
23D  reboot-safe explicit production deploy/operator + provenance      ✅ deployed; active/enabled; MATCH
23E  read-only real SELF E2E + closure                                 pending
```

A production SELF WRITE is not required for 23E unless read-only evidence is insufficient and the
user explicitly approves that real personal-data mutation.
