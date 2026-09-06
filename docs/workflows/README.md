# Workflow Documentation

The reviewable source of permanent credential-free n8n workflows lives under the repository's top-level `workflows/` directory using the n8n Workflow SDK. Source and tests own exact node/error behavior; this directory documents only durable cross-workflow roles that are not clearer in code.

## Current versioned workflows

| Workflow source | Role |
| --- | --- |
| `workflows/odyssey-runtime.ts` | Development/test bridge from n8n to the internal host Odyssey runtime. Not a public product endpoint. |
| `workflows/storage-read.ts` | Low-level contained Markdown read utility. |
| `workflows/storage-write.ts` | Low-level create-only Markdown write utility. |
| `workflows/storage-list.ts` | Low-level contained Markdown path-list utility. |

The three storage utilities predate the current Core application flow and remain useful for development/reference/administrative use. They do not own production semantic mutation; Core owns identity, validation, revision, atomic facts, references, bulk/delete/type-migration behavior.

Cross-workflow storage authority is documented in [Local Storage Boundary](../architecture/storage.md). The current n8n/Core product integration contract lives in the relevant phase architecture documents, especially [Phase 18](../architecture/phase-18-n8n-first-e2e.md) and [Phase 20](../architecture/phase-20-odyssey-online-mvp.md).

## When a separate workflow document is justified

Do **not** create one Markdown file automatically for every workflow. Add a dedicated document only when a workflow has a durable operational/public contract, deployment procedure, or cross-system behavior that is not adequately represented by:

- the Workflow SDK source;
- tests;
- a higher-level architecture contract;
- an ADR/phase document when the behavior is historical or decision-specific.

When a dedicated workflow doc is justified, keep it contract-focused and avoid copying node-by-node source that will drift.
