# Odyssey Web

`odyssey_web/` contains only the browser-side source for the Odyssey Online mobile MVP.
It does not read Markdown, SQLite, Git, pending work, provider credentials, or model configuration.

## Current offline Phase 20.2 checkpoint

The static page sends one same-origin request:

```json
{
  "request": "ordinary natural-language text",
  "request_id": "web-..."
}
```

The expected product response is:

```json
{
  "request_id": "web-...",
  "status": "completed | partial | failed",
  "kind": "answer | acknowledgement | empty | error",
  "message": "human-facing text"
}
```

A new submission gets a new `request_id`. If transport failure leaves the delivery outcome uncertain,
the explicit Retry button resends the same request with the same ID. Ordinary browser state is not
persisted to local or session storage.

The HTML points to `/api/request` through the `odyssey-api-endpoint` meta value. The environment-backed
Phase 20.2 continuation may adapt that same-origin path when the real n8n surface is available, without
widening the browser contract.

## Verification

The repository keeps the frontend dependency-free. CI uses Node's built-in test runner and coverage
support for `client.js`, with an 80% line-coverage gate, plus syntax checks for both JavaScript modules.
Python tests verify the static page contract and guard against external assets, browser persistence, and
`innerHTML` rendering. SonarCloud still analyzes the frontend for code-quality/security findings, while
frontend coverage is excluded from Sonar because the repository does not add an LCOV toolchain solely for
this small framework-free surface.

## Deliberately deferred

This offline checkpoint does not add or validate:

- an n8n serving workflow or real `/api/request` endpoint;
- a provider-backed answerer;
- Cloudflare routing or Access;
- real-vault access;
- persistent chat history;
- microphone/audio capture;
- a frontend framework or build system.

Those environment-facing checks remain part of Phase 20.2/20.3 when the Raspberry is available.
