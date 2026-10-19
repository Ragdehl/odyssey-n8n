# P4 — real n8n webhook to dynamically executed P4 Writer (19 October 2026)

## Demonstrated

The new opt-in test script scripts/odyssey_n8n_dynamic_webhook.py --run exercises the following actual path on Raspberry Pi:

n8n 2.33.7 Webhook POST → fixed synthetic actor/source validator and explicit IF/403 → real n8n HTTP Request → Node loopback proxy INSIDE the isolated container → a bounded Unix-domain socket into the host Python fixture → real P4 RuntimeComposition and Core Writer → physical Markdown in a temporary vault → original deployed DEV Code node Route bounded product result → n8n Respond to Webhook.

Unlike the previous isolated Code-only and webhook tests, the Writer is **invoked during the HTTP request**, not before the workflow starts. The source is the synthetic sentence «Ayer hablé con Maya.» and GPT outputs are recorded fixtures, not live provider calls.

The container uses --network none, --read-only, --cap-drop ALL, --security-opt no-new-privileges and does not publish network ports. Exactly two mounts are permitted: a single read-only generated workflow.json file and a read-only synthetic bridge folder containing a pinned broker.cjs and a private mode-0600 Unix socket. DEV/PROD, /data, home, Docker socket and credentials are NOT mounted. The host-side Python handler uses an exact request-ID, source and conversation-ID allowlist, and operates on one auto-deleted synthetic vault. It is not itself an OS sandbox for a general-purpose connected Codex agent.

## Actual observed results

The authorized first request returned HTTP 200 with status completed, two succeeded Core writes, two affected notes and a graph. Physically, the temporary vault gained a Person named Maya and a Day fact with an implicit SELF link (yo). A second POST with the same request ID returned HTTP 200 via E3 replay with no further recorded GPT calls. **Hashes of all physical Markdown files were identical before and after the replay.**

A wrong request ID returned HTTP 403; a different source with the same ID returned HTTP 403; an unsupported GET returned HTTP 404. The container's own HTTP request was made through n8n and its built-in HTTP Request node, and its response passed through the EXACT Code node deployed in DEV b0fc9b21.

The final run, with a private socket and broker source integrity checks, finished with RC=0 and pass=true. Machine-readable aggregate evidence is held locally in /tmp/odyssey-dynamic-n8n-private-socket-20261019.json. All temporary synthetic assets are deleted at run completion. The readiness attempt counter includes n8n import/publish/start time and is NOT an estimate of product latency.

## Permanent checks

The source contract is covered by tests/runtime/test_n8n_dynamic_webhook_contract.py. The tests are offline: they check exact node graph, original Code preservation, a restricted dynamic HTTP endpoint, safe JSON embedding and source bounds, immutable broker source, rejection of symlink sockets, two small owned temporary mounts and no network or credential access. The tests are part of the standard cross-surface Python and JavaScript gate. The real n8n Docker execution stays opt-in because it launches a whole new n8n instance on a 4 GB Pi.

## Acceptance boundary

This is not yet a full P4 browser n8n GPT integration: the Chromium synthetic test still has its own HTTP facade; live GPT, full production workflow authentication/persistence and Cloudflare Access remain untested. We have proven the previously missing **dynamic n8n→Writer** connection in a safe test fixture only. Full n8n live pipeline with dedicated synthetic actor and vault, browser reload/graph and parallel multi-App semantics remain mandatory for product deployment approval. DEV/PROD were not modified.

## Final verification of change set

The deterministic host gate completed with **1,185 Python tests PASS + 7 subtests PASS and 178 JavaScript tests PASS**. The opt-in actual n8n Docker execution completed with RC=0, true PASS, and verified SHA256 equality across physical notes on same-request replay. An explicit failed verdict causes CLI RC nonzero rather than hiding the failing result in successful stdout. No DEV deploy or production access was performed.
