# UI-1 production promotion evidence

Status: ✅ **COMPLETE** — UI-1 request detail / advanced inspector is deployed and human-verified on the authenticated production product path.

## Release

UI-1 was merged in PR #113 and promoted explicitly to production from commit:

```text
859d72f53adf7c9da9a9a499f0edaaef2b1475cb
```

The production runtime remained healthy with source provenance `MATCH`. The production vault Git HEAD, clean working tree, and pending state were unchanged by the promotion. Cloudflare, credentials, DEV, unrelated n8n workflows, and personal Markdown were not modified as part of the corrective deployment work.

## First authenticated browser checkpoint — failed

The first authenticated production SELF READ returned the expected grounded answer, but the response bubble did not show the UI-1 request-detail `ⓘ` affordance.

Boundary-by-boundary diagnosis proved that the production frontend assets were already current at the host/static-serving/direct-origin layers. The failure was later in the product response path: the active production `odyssey-online` workflow contained an incomplete/old response projection and therefore omitted both `request_detail` and `estimated_cost` from the browser-facing result, even though the selected release source already contained those fields.

This repeated the broader deployment-drift lesson first exposed during Phase 20.3: repository source, runtime provenance, workflow identity, and static assets can all look current while the actually active/published n8n workflow definition is stale.

## Bounded correction

The correction stayed inside the already-approved UI-1 production deployment scope:

- freshly render `odyssey-online` from the selected release commit;
- preserve the existing production runtime target and answerer credential reference;
- republish only the existing production `odyssey-online` workflow identity;
- restart n8n so webhook registration loads the corrected active definition;
- leave the static workflow, Cloudflare, credentials, DEV, personal data, and unrelated workflows unchanged.

Post-correction evidence showed the active online workflow projection contains `request_detail` and `estimated_cost`. The active production online version after correction was:

```text
34c94d58-b6ab-4bc6-a16c-2348095ebd20
```

The static workflow remained unchanged at:

```text
a99ae82e-61f3-46a3-b56f-31a504fec3d9
```

## Final authenticated browser checkpoint — passed

The second authenticated production mobile checkpoint passed:

- grounded SELF READ returned the expected answer;
- the `ⓘ` affordance appeared in the Odyssey response header;
- the request-detail bottom sheet opened successfully;
- estimated whole-request cost was visible (`~$0.002555` for the observed checkpoint request);
- pricing basis was visible (`2026-09-07`);
- planner/retrieval/Git stage evidence was visible in the bounded inspector.

This closes UI-1 production adoption.

## Reusable production deployment rule

For any production promotion that changes a browser-facing n8n workflow, **runtime commit/provenance, workflow ID, and static asset freshness are not sufficient deployment evidence**.

Verify the full boundary in this order:

```text
selected release commit
        |
        v
freshly rendered workflow definition
        |
        v
existing workflow identity updated/published
        |
        v
active n8n version/projection matches rendered definition
        |
        v
webhook registration/reload is current
        |
        v
direct-origin response contains the expected bounded fields
        |
        v
authenticated human browser checkpoint
```

If the product symptom contradicts apparently healthy provenance, diagnose each boundary rather than assuming browser cache or Cloudflare. A deployment is not closed until the active published definition and the authenticated browser behavior both match the selected release.
