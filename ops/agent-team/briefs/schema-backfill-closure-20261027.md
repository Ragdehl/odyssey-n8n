# Schema activation and retrospective property backfill — four-role closure audit

## Purpose
Independently review the single immutable committed candidate for PR #156 on the Odyssey feature branch. The product is local-first with Markdown as authority. Scope is type/property model activation from the Notes UI, schema registry, safe restart, retrospective existing-note scan, E3-guarded optional-property backfill, and safe uncertainty recovery. Audit this feature, not unrelated E4–E6 historical cases.

## Review boundary
Compare the current committed source against ancestor 6c5a197, while prioritizing security and regressions in the later revisions 7d95125, 5116f9b and 473871d. Read the actual new tests, source and canonical docs: docs/architecture/schema-backfill-journal-v1-20261026.md, docs/architecture/functional-roadmap.md, config/note-schema.json. Do not reinterpret earlier reviews as approval of the final SHA.

## Generality
Check arbitrary app-independent type and optional property additions, differences between Core-owned and Apps-owned types, actor-authorized revision changes, exact source/provenance, source-only interpretation semantics, identity ambiguity, and stable schema composition. No fixed sample names or inferred mutable links.

## Quality
Check one-click approval under changing actor/definition, atomic key persistence, exclusive lease/restart, E3 idempotence and CAS, Git crash recovery, malicious/stale/private inventory injection, external note additions and symlinks, journal authenticity, uncertain-write HTTP 409 recovery, actor separation, no credentials and no escalation via browser state. Public scan must not accept caller-supplied stale inventory and must re-verify each page.

## Testing
Review adversarial regression tests and real evidence; distinguish source tests, Chromium localhost->n8n DEV->Core/E3->physical Markdown proof in deployed 4e721a0, and the newer source-only commits. Missing Cloudflare Access authenticated session, real GPT 18-case semantic campaign, new deployed SHA, true background mobile worker or 10k writes must remain explicit gaps. Find concrete missing reproductions, not hypothetical universal coverage requirements.

## Performance
Inspect Raspberry Pi measured synthetic staging with 10k notes (~11 seconds, ~60 MiB RSS), plus 250 serial Git+ContextIndex writes (~37 seconds, p50 ~148ms) and double vault traversal per write. Evaluate risk of 10k actual writes, context index and neural semantically refreshed index, memory constraints on future mobile devices. Require measured evidence, no invented extrapolation.

## Limits / acceptance
Reviewers are read-only; do not deploy DEV or PROD, access personal vault /data/odyssey, change credentials or Cloudflare, run paid provider evaluations, rewrite prompts, or modify tracked code. Use findings with exact file/line and reproducible mechanism, rank only real actionable defects in this feature. PASS with limitations is allowed on the implemented source if code safety is sound, but supervisor must not mark ready_for_user without newly deployed Chromium and GPT acceptance. Four independent model receipts, same SHA. No automatic Builder in first round; no merge or push by agents.
