# UI polish + Notes editing lite

Status: **phase contract approved for bounded implementation; Draft PR work only**.

## Objective

Polish the existing Odyssey Chat/Notes product and expose the safest already-supported Notes mutations without introducing a second knowledge authority, a parallel browser CRUD model, or new application architecture.

This phase is intentionally a short product-finishing pass before Tasks. It should make the current Odyssey knowledge product feel complete enough for ordinary use while preserving the existing Core ownership boundary.

```text
browser UI
   |
   v
existing product/runtime boundary
   |
   v
Core validation + canonical mutation
   |
   v
Markdown + Git/request history + rebuildable indexes
```

The browser may select an already-open stable note/fact and express explicit user intent. It must not become the semantic or persistence authority.

## Architecture challenge

Result: **PROCEED**.

The user-visible problem is not a need for a new Notes editor subsystem. Odyssey already has read-only Notes, stable note identity, write intents (`record`, `amend`, `remove`, `delete`), single-note soft delete, request-correlated persistence, and index refresh. The simplest solution is therefore to reuse those boundaries and add only the smallest missing browser/runtime projection needed for explicit direct editing.

Material caveat: direct Notes mutation is not purely frontend work. Exact fact editing/deletion needs stable current evidence and stale-write protection; free-text fact creation/editing may need the existing semantic/reference-processing path. Any operation that would require cascade semantics, rename semantics, a parallel mutation system, or a new semantic authority is out of scope rather than being improvised in UI code.

## Existing capabilities to reuse

- `odyssey_web` already owns Chat + read-only Notes presentation and same-origin Notes transport.
- `/api/notes` already supports bounded `capabilities`, `query`, `intelligent`, `detail`, and `backlinks` operations.
- Core already owns `KnowledgeUnit` write intents including `amend`, `remove`, and `delete`.
- Single-note deletion already uses recoverable soft-delete semantics.
- Canonical Markdown remains authoritative; Git/request history and index refresh already follow successful writes.
- UI-1 request detail already exposes bounded safe operational/model/timing/usage evidence after a request completes.
- UI-2 already has stable note navigation, backlinks, historical result snapshots, and affected-note snapshots.

## Acceptance criteria

### A. Product polish

1. Chat and Notes retain the existing two-surface product model and state preservation.
2. Notes list/detail, loading, empty, success, clarification, and error states receive a coherent mobile-first visual pass without changing semantic behavior.
3. The existing request inspector is easier to discover/read but remains progressive disclosure and exposes only already-approved bounded evidence.
4. While a normal request is pending, Chat may show one neutral truthful busy state such as `Odyssey está trabajando…`; it must not fabricate execution stages.
5. Existing Note links/backlinks/navigation remain stable and readable.

### B. Explicit fact mutation from an open Note

A direct-edit mutation must target the stable note already open in Notes and must re-ground current canonical state before commit.

The phase may expose the following operations only when they can reuse current Core mutation semantics safely:

- **delete one existing fact** using stable current fact evidence/locator and stale-state validation;
- **edit one existing fact** only if the implementation can preserve/revalidate references through the existing Core semantic/write boundary rather than treating rendered browser text as authoritative Markdown;
- **add information to the selected Note** only if free-text input can reuse the normal Odyssey semantic/reference-processing path while keeping the selected stable note as the explicit target.

If edit/add cannot meet those conditions with a small bounded bridge, the UI may leave those controls unavailable in this phase rather than introducing a parallel mutation path.

After a successful mutation:

- canonical Markdown is durably updated;
- request/Git history remains attributable;
- rebuildable indexes refresh through the normal path;
- the Note detail refreshes from canonical current state;
- stale/conflicting state fails closed rather than silently overwriting newer content.

### C. Safe Note deletion

The phase may expose delete for one selected Note only under existing soft-delete semantics and only when the current canonical state proves no unresolved incoming-reference/cascade decision is required.

If incoming backlinks/references make deletion semantics ambiguous, the UI must refuse the destructive action with a clear bounded explanation. It must not silently remove referring facts, create broken links, or invent cascade policy.

### D. Deterministic validation

- Browser request/response unions remain allowlisted and validated.
- New mutation paths have focused Core/runtime/web tests.
- Existing read-only Notes behavior remains covered.
- No production model-facing prompt/schema change is required merely for visual polish or deterministic direct mutations.
- If implementation materially changes a production model-facing contract, stop and apply the normal focused live-evidence gate before readiness.
- Full deterministic CI and Sonar must be green before Ready.

## Out of scope

- note rename;
- multi-select or bulk delete;
- delete cascades or automatic backlink cleanup;
- permanent/hard delete semantics;
- unrestricted Markdown editor;
- browser-owned CRUD persistence;
- `@` autocomplete/link picker;
- new note types/schema/ontology;
- new database, service, queue, framework, or model stage;
- Activity/history UI;
- real-time execution-stage progress (#136), SSE, polling status infrastructure, or cancellation;
- Tasks, Calendar/Events, Reminders, Projects;
- new authentication/permission model;
- DEV/PROD deployment as part of implementation work without separate human authorization.

## Open decisions

None for the first bounded slice.

Potential edit/add controls are conditional implementation outcomes, not product ambiguities: they ship only if the existing Core semantic boundary can be reused safely with a small bridge. Otherwise they remain deferred without blocking the visual polish/fact-delete/eligible soft-delete slice.

## Implementation order

1. Product/UI polish and neutral pending state, preserving current behavior.
2. Expose bounded stable fact-edit metadata from Core/runtime only as needed; do not expose raw Markdown authority.
3. Implement exact single-fact delete with stale-state protection.
4. Evaluate edit/add reuse against the existing semantic write path; implement only if the bridge stays small and authority remains in Core.
5. Implement eligible single-note soft-delete guarded by current incoming-reference evidence.
6. Run focused tests, full deterministic verification, semantic review, then isolated DEV validation under the normal human-gated deployment process.

## Relationship to existing direction

This phase deliberately advances a small subset of the future UI-4 direction before Tasks because real use now benefits from finishing the current knowledge surface. It does not approve the broader UI-4 rename/cascade/multi-edit contract in issue #134. Tasks remains the next significant application phase after this bounded product-finishing pass.
