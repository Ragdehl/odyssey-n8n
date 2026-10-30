# C4 deferred diagnosis: independent re-audit of actionable fixes

## Pinned increment and prior findings
Audit the **new** ChatGPT correction delta since `51151b0b3f02719dfadd5e6df8ca4b810c4d49b0`; inspect relevant existing contracts before judging. The prior audit `c4-deferred-4role-v2-20261029` on 51151b0 had four genuine reviews: Generality FAIL (lost browser stage_view; ungrounded SOME; n8n changed Core status), Quality FAIL (history dropped E2; pagination did not attach sidecar; false SOME), Testing FAIL (same gaps plus no current SHA E2E), Performance BLOCKED (missing Pi metrics). Those results are historical and **cannot be inherited** as PASS.

## Expected repaired behavior
- E3 immutable result remains the only authority; actor/fingerprint/SHA256 binding and at-most-once C4 worker unchanged. No new writer, DB, service, credential scope or NoteSchema.
- Browser validation preserves only the bounded Core-owned `stage_view`, without elevating model text. A read-only authenticated `diagnosis` lookup re-reads the original actor-scoped SHA-verified E3 receipt and returns minimal failed-stage, reason/status and write-evidence proof. It reveals no source, paths, note IDs or names, and no raw arbitrary model prose. Historical ConversationStore deliberately remains lean: E2 is not copied into it.
- Browser verifies the sidecar against that E3 proof, and against the independent original E2 if present. Contradictory statuses, stages, parent-child provenance or write claims are rejected. Reload and older paginated assistant replies can attach bounded advice, never update original text/receipt.
- n8n CANNOT_ANSWER retains the actual Core `partial`/`needs_attention` instead of rewriting to `failed`; without confirmed writes it stays `cannot_answer` with no success acknowledgement or invented snapshot.
- Reviews must focus on evidence, provenance, privacy, model authority, replay, races, UI and actual performance—not merely passing suites. Distinguish *repairable* defects from missing external deployment/provider acceptance.

## Deterministic and Pi synthetic evidence
Authoritative source gate: **2,460 Python + 7 subtests + 278 JavaScript PASS**; focused HTTP/actor and UI reload/page/projection/forgery tests also pass. Reproducible Pi scripts `scripts/odyssey_c4_deferred_perf_pi.py` and `scripts/odyssey_c4_deferred_concurrency_pi.py`. Eight fake-provider requests per mode: synchronous response p50/p95 367.6/368.5 ms; deferred response 11.1/11.2 ms; deferred final diagnosis 380.1/388.4 ms. Fake provider delay exactly 180 ms per call, two calls per success, no network/provider. RSS ~78.5–82.2 MiB, swap process 0, thermal 45.75–47.95 C. Three quick requests: max 2 concurrent fake provider calls, two finished diagnoses and one unavailable fallback, no Markdown changes. Neither benchmark establishes GPT-real p95, Android, nor long-running load.

## External acceptance still missing
No new billable real GPT evaluations authorized for the revised semantic prompt, no current-SHA authenticated HTTPS browser→actual n8n→fresh model→Core/E3→physical Markdown→Notes/Calendar reload test, no DEV deployment, no PROD operations, no user data. Flags OFF. Four-role source review does NOT grant deployment/merge. Base PR #161 includes additional historical issue #157 work outside this incremental review; do not claim it all audited.
