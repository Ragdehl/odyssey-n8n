# Phase 22A — self-identity architecture contract

Status: **22A design complete; 22B identity-boundary foundation complete; 22C binding complete; 22D provenance complete; 22E self resolution complete; 22F next.**

This document owns the Phase 22 contract and decisions. The broader product direction and
examples remain in [Future user self-identity binding](future-user-self-identity.md).

## Objective

Odyssey knows which ordinary canonical `person` note represents the authenticated/current human,
and first-person requests can resolve deterministically to that note. The note remains ordinary
Markdown knowledge; the user binding remains durable non-knowledge identity state.

```text
authenticated actor identity -> provenance human actor ID
authenticated actor identity -> stable user/person binding -> canonical person note ID
```

## Current boundary evidence

The protected production path is:

```text
Cloudflare Access -> cloudflared tunnel JWT validation -> n8n -> runtime -> Core
```

Access authentication is established at the edge/tunnel boundary. The standard Access assertion
is carried as `Cf-Access-Jwt-Assertion`; standard identity projections may include
`Cf-Access-Authenticated-User-Email`, but the checked-in n8n workflow does not extract a human
claim or stable user ID. The runtime accepts only `request` and optional `request_id`, and records
the static application actor from `ODYSSEY_ACTOR`. Production evidence shows
`created_by.human` and `updated_by.human` are currently null.

The validated Access JWT `sub` claim (or an equivalent issuer-scoped opaque subject explicitly
exposed by the trusted adapter) is the external-principal subject, not Odyssey's durable user ID.
Email is human-readable and can change, so it is not a durable key. The mapping repository
converts the validated `(issuer, subject)` pair into a newly generated Odyssey-owned UUID. No
provider identity value is used as `created_by.human`, and no identity value is recorded here.

## Contract decisions

### Trusted conversion boundary

The smallest safe conversion is a trusted integration adapter after Access validation and before
Core execution. n8n may orchestrate extraction, but raw browser-supplied identity headers must
never be trusted. The adapter resolves the validated external principal through the identity
mapping repository, maps it to an Odyssey-owned `stable_user_id`, and passes typed context to the
runtime. Core receives neither raw headers nor JWTs, email, provider subjects, or credentials.

### Runtime request contract

Extend the current envelope with one optional typed actor context while preserving `request_id`:

```json
{
  "request": "¿Dónde trabajo?",
  "request_id": "trusted-correlation-id",
  "authenticated_actor": {"stable_user_id": "odyssey-owned-uuid-v4"}
}
```

The runtime validates the shape, rejects empty/unsafe IDs, and rejects unrecognized fields.
`stable_user_id` is opaque and never a display name. The internal Core context carries the same
typed identity to provenance and deterministic self resolution. `ODYSSEY_ACTOR` remains the
separate application actor.

### External-principal mapping persistence

Persist a small versioned mapping in durable non-knowledge state under the configured state root,
preferably `state/identity-mappings.json`, with the existing root guard and atomic restrictive
writes:

```json
{"format": "odyssey_identity_mapping", "format_version": 1, "principals": [{"issuer": "...", "subject": "...", "odyssey_user_id": "..."}]}
```

The external-principal mapping above references no canonical note. The separate 22C self-binding
state maps only `odyssey_user_id` to `person_note_id`:

```json
{"format": "odyssey_self_bindings", "format_version": 1, "bindings": [{"odyssey_user_id": "...", "person_note_id": "..."}]}
```

It is not a Markdown fact, profile copy, alias, provider mapping, or authorization grant. A
repository abstraction owns note validation and atomic update; no new database or service is
justified.

### First-person resolution

The planner/request contract should represent an unambiguous first-person target explicitly (for
example, a validated `self` target scope), without adding `yo`, `me`, `mi`, or other language
aliases. Before ordinary semantic identity search, the deterministic resolver maps that scope to
the actor binding and verifies an active canonical `person` note. Relational targets such as
“mi hermano” remain distinct from the self target.

### Fail-closed behavior

- Missing actor context for a first-person target: no guess and no mutation.
- Missing binding: stable needs-attention result requiring explicit binding.
- Missing, deleted, invalid, or non-`person` bound note: needs-attention; require rebinding or
  recreation, never name/similarity selection.
- Malformed or duplicate binding state: reject identity resolution and mutation until repaired.
- A binding grants no retrieval or mutation authorization; authorization remains separate.

Generic requests that do not require self identity may retain existing behavior, subject to the
ordinary authentication/authorization boundary.

## Scope decomposition and architecture challenge

Result: **PROCEED**. The current request path already has a narrow n8n-to-runtime contract and a
durable state root. A new service, profile store, permanent `develop` branch, or model-based
identity guess would add unnecessary authority and failure modes.

Actor provenance and self binding are separate implementation slices over one shared typed
request-identity contract. Provenance can be introduced and verified without changing planning;
binding can then be explicitly established and consumed by the resolver. Coupling them into one
large subphase would make authentication, account state, and knowledge mutation harder to review.

## Implementation sequence and acceptance criteria

### 22B — trusted actor context — complete

The runtime now accepts an optional exact `authenticated_actor.stable_user_id` envelope containing
only an Odyssey-owned UUIDv4, forwards it as typed context to Core, and rejects provider-shaped
or extra fields. `IdentityMappingRepository` persists validated external `(issuer, subject)` pairs
to Odyssey-owned UUIDs using versioned guarded JSON and atomic restrictive writes. This foundation
does not extract identity from the browser, change Cloudflare, bind a real person, or write human
provenance yet. Deterministic boundary, spoofing, two-principal, and malformed-state tests pass.

### 22C — durable binding state — complete

The guarded `SelfBindingRepository` now persists only an Odyssey user ID and an active canonical
`person` note ID. Initial binding is idempotent; conflicting binding requires explicit compare and
swap rebind with the expected previous note ID. Test coverage includes target validation, rename
stability, malformed state, and synthetic multi-user separation. No real person is bound.

### 22D — provenance propagation — complete

The trusted runtime composition combines the validated `AuthenticatedActorContext.stable_user_id`
with the existing `ODYSSEY_ACTOR` application identity immediately before Core persistence:

```text
AuthenticatedActorContext(stable_user_id) + ODYSSEY_ACTOR
        -> {"human": stable_user_id, "app": application_actor}
        -> existing normalize_actor_provenance() and lifecycle persistence
```

CREATE records both values in `created_by` and `updated_by`; UPDATE, DELETE, and type migration
preserve creation provenance and attribute the lifecycle update to the current pair. `NO_CHANGE`
does not rewrite provenance. Calls without authenticated context retain the compatibility form
`{"human": null, "app": ODYSSEY_ACTOR}`. Provenance does not require a self-person binding and
never records provider subjects, email, JWTs, display names, or person note IDs.

### 22E — deterministic self resolution — complete

The planner emits only the nullable semantic `self_target: "self"` signal on the shared
`SelectionCriteria`; it emits no user, person-note, provider, email, or filename identity. Core
resolves that signal before ordinary exact or semantic identity work through the existing
`SelfBindingRepository`, obtaining the stable `person_note_id` and revalidating its active
canonical `person` note.

SELF retrieval passes only the bound stable note ID as an authoritative candidate restriction to
the existing context index. SELF writes pass directly into existing UPDATE preflight and cannot
fall through to CREATE. Missing actor, missing/malformed binding, deleted or non-person target,
and invalid identity state return the existing deferred/needs-attention path. Ordinary named and
relational targets remain unchanged; possessive wording alone does not activate SELF.

### 22F — focused adoption gate

Run deterministic Core/runtime/workflow checks and a focused DEV validation only after the identity
boundary is approved. Production binding or real-person use remains a separate explicit human
gate. Validate per-actor key separation and ordinary note/search/statistics behavior.

## Observed 22B implementation evidence

The code path is currently intentionally limited to:

```text
trusted adapter (future external-principal validation/mapping)
        -> AuthenticatedActorContext(odyssey_user_id)
        -> runtime HTTP boundary
        -> Core execution boundary
```

The current browser/n8n path has not been changed to manufacture or forward identity, so an
untrusted client cannot spoof a human actor through headers. No provider subject is passed into
canonical note metadata or provenance; provenance propagation remains 22D.

## Observed 22C implementation evidence

The mapping and binding files are separate durable state:

```text
(issuer, subject) -> identity-mappings.json -> odyssey_user_id
odyssey_user_id  -> self-bindings.json       -> person_note_id
```

The self-binding repository stores no provider principal, email, display name, filename, alias,
or copied fact. It resolves the target against the canonical repository by stable note ID and
requires exactly one active note with type `person`.

## Observed 22D implementation evidence

Deterministic lifecycle tests cover authenticated CREATE and UPDATE, distinct Odyssey users,
app-only compatibility, `NO_CHANGE`, DELETE, and type migration. They verify that only the
Odyssey-owned stable user ID reaches human provenance and that an existing self binding is not
required for provenance.

## Observed 22E implementation evidence

Deterministic coverage proves bound self READ and UPDATE behavior, same-name isolation, rename and
filename stability, two-user separation, missing/deleted/non-person fail-closed behavior, no
fallback CREATE, and preservation of ordinary relational/named targets. The focused live planner
gate used five synthetic cases with five completed `gpt-5.6-luna` low-effort/no-retry calls and
no Sol fallback. It emitted SELF for direct “where I work” retrieval and “record where I live”,
and no SELF signal for relational, possessive, or ordinary named-person sentinels. Reported usage
was 57,995 input tokens (57 ordinary and 57,938 cached), 573 output tokens, and an estimated
`$0.001858` under the retained 2026-09-07 pricing snapshot. One initial schema-validation API
submission failed before model execution and reported no usage; the strict schema was corrected
and the five-case gate then passed. An earlier post-fix harness attempt completed one additional
Luna call before crashing while reading local usage metadata; its provider counters were not
retained, so the captured amount is a verified lower bound rather than a total for every call.

Phase 22A–22E acceptance is met when the actor, external principal, Odyssey user, and person are
distinct; the external source is an issuer-scoped opaque subject; the mapping generates and
validates an Odyssey-owned ID; runtime identity is typed and validated; mapping state is durable
non-knowledge state; self resolution is deterministic and precedes semantic search; invalid
identity state fails closed; and the design supports per-actor mappings without implementing
multi-user authorization. No provider calls or production data are used in 22A.
