# Phase 23 — production self-identity adoption

Status: **23A repository + live production-boundary inventory complete; 23D reboot-safe production operator implemented but not deployed. 23B remains pending after current production-runtime/tunnel recovery. No identity/data/deploy mutation is authorized without its explicit human gate.**

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

The production browser workflow still deliberately omits `authenticated_actor`; only DEV rendering
injects the synthetic actor. `IdentityMappingRepository` is not yet wired into the production
request path.

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

### Open evidence required before implementation

A read-only live inventory must establish, without printing secret/token values:

1. Which Cloudflare Access identity headers actually reach the current production n8n webhook after
   tunnel-side JWT validation.
2. Whether the validated assertion available at n8n contains the expected issuer-scoped `sub` and
   the claim/audience shape required to identify the existing Access application; report claim
   names/shape only, not real values.
3. The current production n8n workflow/deployed-source identity and the exact private runtime target.
4. The current production runtime service/environment roots (`vault`, `state`, `runtime`) and
   application actor, without exposing secrets.
5. Whether the deployed production operator/service provenance matches the approved source. The
   tracked `odyssey-prod` operator exposes this as `MATCH`, `DRIFT`, or `UNKNOWN`; no live
   deployment is implied by its implementation.

No new authenticated product/model request is required for this inventory if retained execution
metadata can establish the header/claim shape safely.

## Architecture challenge

Result: **PROCEED, with one live-boundary evidence dependency before implementation.**

The real problem is trusted identity projection and controlled production promotion, not new
knowledge semantics or new authentication infrastructure. Phase 22 already owns mapping, binding,
provenance, and deterministic SELF behavior; Cloudflare/cloudflared already own Internet
authentication and token validation. Phase 23 should connect those existing boundaries with the
smallest trusted adapter and an explicit production deployment operator.

Do not hard-code one production `stable_user_id` into the browser workflow merely because the
current Access policy has one user. That would make policy membership an implicit identity mapping
and could silently impersonate a newly allowed Access user later. The production request must be
projected from the validated principal on each request.

Do not move `identity-mappings.json` ownership into n8n. Core already owns the durable identity
mapping contract. The exact integration shape (for example, a narrow private runtime identity
adapter orchestrated by n8n) should be chosen only after the live inventory confirms what validated
principal material reaches n8n. No additional service is justified.

## Production operator requirement discovered during adoption

The Phase 23 live inspection found that the previously working production runtime had been launched
as a transient user unit and was no longer present after a Raspberry reboot. The current production
contract can be reconstructed safely from stable configuration, but the former one-off transient
launch metadata itself was volatile. This is operational debt, not a self-identity semantic failure.

After the current recovery and identity adoption work, the next production-hardening step is the
smallest `odyssey-prod` operator/service that makes production reproducible and reboot-safe while
remaining human-gated for promotion:

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

This must not become automatic merge-to-PROD promotion. The automation is inside the explicit
operator; the human production gate remains. n8n workflow provenance remains a future read-only
verification concern and is outside the runtime service lifecycle.

## Planned sequence after 23A

```text
23A  repository + read-only live boundary inventory                    ✅ complete
23B  trusted validated-principal -> Odyssey-user projection            pending after runtime/tunnel recovery
23C  explicit real-user -> existing person binding                     pending human data gate
23D  reboot-safe explicit production deploy/operator + provenance      implemented; human deploy gate
23E  read-only real SELF E2E + closure                                 pending
```

A production SELF WRITE is not required for 23E unless read-only evidence is insufficient and the
user explicitly approves that real personal-data mutation.
