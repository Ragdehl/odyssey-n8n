# Phase 22A — self-identity architecture contract

Status: **22A design complete; implementation not started.**

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

The preferred future source is the validated Access JWT `sub` claim (or an equivalent
issuer-scoped opaque subject explicitly exposed by the trusted adapter), not email. Email is
human-readable and can change; the opaque subject is suitable as a stable key only within its
validated issuer/team/audience boundary. No identity value is recorded here.

## Contract decisions

### Trusted conversion boundary

The smallest safe conversion is a trusted integration adapter after Access validation and before
Core execution. n8n may orchestrate extraction, but raw browser-supplied identity headers must
never be trusted. The adapter maps the validated subject to `stable_user_id` and passes typed
context to the runtime. Core receives neither raw headers nor JWTs, email, or credentials.

### Runtime request contract

Extend the current envelope with one optional typed actor context while preserving `request_id`:

```json
{
  "request": "¿Dónde trabajo?",
  "request_id": "trusted-correlation-id",
  "authenticated_actor": {"stable_user_id": "issuer-scoped-opaque-id"}
}
```

The runtime validates the shape, rejects empty/unsafe IDs, and rejects unrecognized fields.
`stable_user_id` is opaque and never a display name. The internal Core context carries the same
typed identity to provenance and deterministic self resolution. `ODYSSEY_ACTOR` remains the
separate application actor.

### Binding persistence

Persist a small versioned mapping in durable non-knowledge state under the configured state root,
preferably `state/identity-bindings.json`, with the existing root guard and atomic restrictive
writes:

```json
{"schema_version": 1, "bindings": {"stable-user-id": {"person_note_id": "stable-person-note-id"}}}
```

The binding references only a stable canonical note ID. It is not a Markdown fact, profile copy,
alias, or authorization grant. A repository abstraction owns validation and atomic update; no new
database or service is justified.

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

### 22B — trusted actor context

Add typed runtime validation and the trusted adapter projection. Test accepted/rejected envelopes
and ensure raw browser headers cannot supply identity. No production deployment or Cloudflare
change is implied.

### 22C — durable binding state

Add the guarded state repository and explicit bind/rebind operation against a selected stable
`person` note. Test atomic persistence, malformed state, missing/deleted notes, and two synthetic
users with distinct bindings.

### 22D — provenance propagation

Record the validated stable user ID in `created_by.human`/`updated_by.human`, preserving the app
actor. Test request correlation and human-null autonomous actions.

### 22E — deterministic self resolution

Add explicit self-target planning/resolution before semantic search. Test self retrieval/update,
relational targets, rename-by-stable-ID, missing/ambiguous bindings, and no alias hacks.

### 22F — focused adoption gate

Run deterministic Core/runtime/workflow checks and a focused DEV validation only after the identity
boundary is approved. Production binding or real-person use remains a separate explicit human
gate. Validate per-actor key separation and ordinary note/search/statistics behavior.

Phase 22A acceptance is met when the actor and person are distinct; the preferred identity source
is an issuer-scoped opaque subject; runtime identity is typed and validated; binding state is
durable non-knowledge state keyed to a stable note ID; self resolution is deterministic and
precedes semantic search; invalid identity state fails closed; and the design supports per-actor
bindings without implementing multi-user authorization. No provider calls or production data are
used in 22A.
