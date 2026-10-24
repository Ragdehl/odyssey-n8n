# C1–C4 / Tasks — independent four-role closure review (DEV only)

**Human goal 24 October 2026:** stop nonessential Tasks latency optimization;
close the integrated C1–C4 chat/error-guidance stage without changing Core/E3
semantics and then start a new feature stage for extending note properties/types.

## Immutable candidate and scope

Review committed `dev` source against the earlier formal C4 audit baseline
`5765587a6a4889757ff2d956a472ab38879a974c` (the previous four-role
review failed/blocked with actionable findings now claimed repaired). Focus
runtime `conversation_error.py`, `composition.py`, `whole_source_light.py`,
`dev_hot_path_diagnostics.py`, workflow `odyssey-online.ts`, web app/client,
the C1–C4 contracts, Tasks and WorkSession integration, and associated
regressions. Read only; no code changes, deploys, credential/network changes,
PROD or private Markdown reads/mutations. Do not restart historic E4/E5/E6.

## Safety and required decisions

Verify an untrusted model cannot authorize any canonical mutation; E3/Core
alone decide, verified receipts and actor/request-scoped idempotence survive
retry, and n8n refuses forged status/guidance, contradiction, unknown writes,
partial writes and invalid reason code. Inspect for scope truncation, missed
second Task operation, semantic identity uncertainty and invalid fallthrough.
Judge current DEV acceptance with **bounded evidence, not hypothetical universal
correctness**. A review may PASS with explicit limitations only if the C4
contract being accepted is actually exercised; otherwise verdict BLOCKED/FAIL
with actionable evidence. Four independent roles: generality, quality,
testing, performance.

## Available host evidence (verify all claims; no invented PASS)

* DEV checked out/deployed `050f26f6ce9330bbb7c694fdf8b21db2feb067ac`;
  later source commits are documentation-only. PROD and DEV health HTTP 200.
* Offline full gate on functional DEV source `050f26f`: 2,058 Python tests,
  199 JS, 12 cross-surface groups PASS, log
  `/tmp/odyssey-p4-phase-timing-gate-20261024.log`.
* DEV Chromium user UI->n8n->real GPT->Core/E3->UI+reload tests for real
  Chat and synthetic nonexistent WorkSessions PASS, no note mutation; E3
  independent physical receipts contain Tasks interpretation/resolution spans.
  Files under `.odyssey-agent-runs/p4-breakdown-dev-adoption-20261024/`.
* DEV Chromium realistic presence forwarded via n8n; 2 user requests,
  WorkSession semantic search 540ms and 35ms; Tasks interpretation 8.62s
  and 7.42s, no loss of identity checks. Evidence in
  `.odyssey-agent-runs/p4-worksession-real-presence-20261024/`.
* **Same-ID UI recovery verified** from real browser click: test proxy
  simulates loss of an actual HTTP 200 AFTER n8n finished, user presses
  visible retry button, n8n receives same request ID twice (200/200),
  first HTTP 26.461s vs replay 0.867s, immutable physical delivery result
  byte-identical, only one user bubble, 166 Markdown byte-identical.
  The public n8n JSON projection intentionally does not expose the internal
  `delivery_replayed` field, so a private harness initially mislabeled
  that check FAIL; after checking true trust boundary, 11 independent observable
  assertions all PASS. Evidence `c4-ui-retry-acceptance-20261024/validated-retry.json`.
* E3 physical Writer+controlled post-write `partial/SOME`, JS compiled
  workflow projection, browser validator and immutable replay verified in
  synthetic temporary vault, **NOT a naturally triggered real browser partial**.
  See `docs/architecture/conversation-chat-c4.md` and test
  `tests/runtime/test_conversation_error.py`.
* Strictly outstanding: no successful Cloudflare Access browser session from
  outside the authorized Raspberry/local proxy, no natural C4 partial from
  the public Chromium user path. Neither should be silently converted to PASS.

## Audit outcome sought

Return per-role verdict and precise defects, distinguish blocking correctness
from optional performance. No prompt/model/independent Task attestations may
be removed for speed. Report exactly whether **DEV-scoped stage** is
conditionally acceptable and which tests remain for promotion. Do not
approve promotion to PROD. Avoid calling models solely to benchmark latency.
