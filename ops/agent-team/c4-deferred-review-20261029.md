# C4 deferred diagnostic: independent four-role audit — Issue #157

## Frozen source boundary
Review the ChatGPT-authored, committed **increment** from `9a1249369141311d6222d3c9db353f054c909179` to the pinned feature HEAD (including this short audit handoff). The full PR #161 since `dev` exceeds the supervisor's evidence-size limit; do **not** claim four-role coverage of that whole earlier diff. Relevant contract: `docs/architecture/conversation-chat-c4.md`, `docs/architecture/issue157-generic-day-recollection-routing.md`, `AGENTS.md`. Prior independent semantic checks on other SHAs are historical evidence only.

## Requirements under review
- The original Core/E3 result and immutable, idempotent delivery receipt must be saved once and returned without waiting for optional, post-write C4 diagnosis; prewrite source reinterpretation stays on the synchronous safe path and cannot be retried from the sidecar.
- Authenticated, actor-scoped lookup bound to the exact receipt digest and fingerprint; no source or note IDs leaked. Worker has bounded concurrency, crash recovery is *at most once*, no replay/write authority, no extra DB/service.
- A rejected, untrusted, unavailable or crashed model must never alter the base reply, misattribute E2 stage, forge a write status, introduce an unauthorized prompt or extend a UI retry into a mutation.
- Browser and n8n must validate exact typed fields, stage, owner route, Core label, status and write evidence; no model prose or HTML injection; genuine historical replies remain intact after reload/pagination.
- Inspect concurrency races, durability fsync/atomic link failures, lock boundaries, pending status, provider spend and real user latency. Check method contracts, tests and regression coverage rather than accepting a green suite alone.

## Observed evidence and known limitations
Local official gate on source: 2,459 Python (+7 subtests) and 273 JS PASS; Ruff, formatter, docs, schema and GitHub CI PASS at `c6c235b` before this handoff file. No fresh GPT real semantic evaluation on the corrected prompt, no authenticated current-SHA browser/n8n/provider/Core/Markdown E2E, and no post-change DEV deployment. Flags default OFF. DEV marker remains `4ba8bb8`; PROD/private vault off limits.

## Audit behavior
Each reviewer independently returns precise evidence-backed findings for **this increment**, marks existing missing external acceptance as BLOCKED rather than authorizing deployment, and does not re-run live GPT tests or ask for credentials. Distinguish actionable source defects from inherently missing external evidence. Read-only round; no Builder edits, reset, merge or deploy. Four roles: Generality, Quality, Testing and Performance. Compare against exact parent SHA, not the entire PR. No false PASS for broader Issue #157 or product acceptance.
