# DEV 19 Oct 2026 — invisible navigation/send buttons, confirmed public route drift

## Reported symptom

The mobile Brave screenshot of https://odyssey-dev.ragdehl.com/api/odyssey showed the Odyssey title but the three navigation button frames and the purple Send button had **no icons**. The chat surface was blank. DEV and PROD origins were running normally.

## Root cause — independently verified

The deployed DEV web package is from commit `b0fc9b21`. Its `app.js` has a **static ES-module import** of `./presence.js`, an optional DEV ONNX embedding warmup helper. Module imports are all-or-nothing. Cloudflare is configured to forward only explicit public routes.

Read-only Cloudflare control-plane inspection (tunnel config version **12**) showed:
- Actual DEV public routes: 14.
- Contract inventory routes: 15.
- **Only missing route: GET /api/presence.js**.
- No unexpected public routes; the separate production ingress remained present.
- Inside DEV, `http://172.18.0.1:28780/api/presence.js` returned **HTTP 200, text/javascript**.
- Public route inspection returned `DRIFT`, despite DEV backend `/healthz` being HTTP 200.

No Cloudflare or PROD modification was performed. This is the same class of problem previously encountered with omitted ES modules in the DEV public tunnel.

## Browser-level causal reproduction

A read-only localhost proxy with the actual deployed DEV web assets, using Chromium ARM64 390×844, reproduced both cases without sending any new message:
- Simulated absent `presence.js`: 0 navigation SVG, 0 Send SVG, 0 chat nodes, no DEV marker.
- Route available: 9 navigation SVG, 1 Send SVG, 41 chat elements, DEV marker present.
- An additional Chromium experiment served the candidate `app.js` **from the development branch only** while continuing to block `presence.js`: **9 navigation SVG, 1 Send SVG, 41 chat nodes, marker present, 0 JavaScript exceptions**. Thus the fallback is a verified safety improvement.

Local machine-readable output: `/tmp/odyssey-missing-presence-compare-20261019.json`, `/tmp/odyssey-dev-lazy-presence-pass-20261019.json`.

## Source hardening completed (not yet deployed)

1. `odyssey_web/app.js`: replaced unconditional `import {startEmbeddingPresence} from "./presence.js"` with **optional lazy import wrapped in a rejection handler** on DEV. The optimization may fail without aborting the application's main ES-module graph.
2. `tests/test_odyssey_web_static.py`: accepts optional `presence.js` outside the **critical static dependency graph**, while still requiring the route to exist in the source workflow and public inventory.
3. `tests/odyssey_web_app.test.mjs`: removes its old static import rewrite; existing app DOM suite passes.
4. `scripts/odyssey-dev`: added **fail-closed public-route preflight before any deployment service restart**. A `DRIFT` or `UNKNOWN` cannot be presented as a successful deployment. Existing DEV status already reports `public_route_provenance=DRIFT`.
5. `tests/test_odyssey_dev_operator.py`: verifies the preflight ordering and refusal of `DRIFT` and `UNKNOWN`.

The source change protects the **next** deployment, but it does NOT update the currently running DEV web assets and does NOT restore the user-facing mobile UI until the live Cloudflare route is corrected or a separately validated minimal hotfix is deployed.

## Immediate action awaiting explicit authorization

The existing bounded operator `scripts/odyssey_dev_public_routes.py update --authorized-dev-change` can reconcile exactly the missing **/api/presence.js** path, preserve hostname-wide Access, preserve the PROD ingress, preserve the target DEV origin, and maintain the deny-by-default tunnel fallback. Its guards perform readback to verify only the approved route change. It requires **explicit user authorization for Cloudflare DEV configuration**; the screenshot and general 'seguir' instruction alone have not been treated as that authorization. No external route has been changed here.

After approval, update only that route, verify public status `MATCH` and Chrome/Brave after a reload. Do **not** deploy the full P4 branch for this UI problem; P4 product acceptance remains pending.
