# Weekend regression and audit — DEV, 22 October 2026

**Goal:** verify Odyssey is demonstrable in the browser with genuinely live
GPT→n8n→Core/E3→Markdown→Calendar/Notes, not just isolated backend tests.
No PROD code or data modified. Development base `5951830` deployed at
start, active public DEV runtime 200 and n8n 200.

## Accumulated deterministic gate

- Original audit candidate: **1850 Python PASS +181 JavaScript PASS**.
- New blocker regression applied after audit: **1856 Python PASS +181 JavaScript PASS**, 134 files, 11 groups, acceptance ledger **21 invariants / 58 anchors**.
- Files: `/tmp/odyssey-weekend-regression-gate-20261022.log`,
  `/tmp/odyssey-weekend-audit-fix-full-gate.log`.

## Real UI trial: Task + Subtask + Work Session

Using Chromium mobile 390×844 with actual deployed DEV JS, clicks and
authenticated DEV proxy limited to one synthetic parent Task:

1. Chat creation of Task: PASS, real GPT/n8n, receipt "Guardado".
2. Graph detail: PASS; one route lane, no legacy diagnostic fallback,
   13 SVG elements.
3. Notes search/detail of Task: PASS, uniquely matched parent.
4. Create Subtask: PASS (new canonical Task id).
5. Complete and reopen Subtask via parent's checkbox: PASS, two E3
   mutations with no frontend errors.
6. Work Session start: PASS; canonical session id returned.
7. Activity add: PASS, then activity edit: PASS.
8. Work Session stop: PASS.
9. Browser reload and conversation retention: PASS.
10. Physical note readback via DEV /api/notes: parent + child
    `pending`, one ended Work Session, one activity.
11. JS exceptions: **0**; API errors: **0**.

Artifact:
`/home/ragdehl/projects/.odyssey-agent-runs/weekend-ui-task-subtask-session-20261022.log`.
All writes limited to synthetic names/ids, no PROD access.

Previous UI PASS evidence on `5951830`:
`e6-ui-verified-event-20261022.log`,
`e6-ui-verified-task-20261022.log`,
`e6-ui-calendar-views-20261022.log` and
`e6-direct-flow-second-acceptance-20261022/e2e.log`.
These prove Event/Task, graphs, notes, calendar month/1/3/7-day,
wrong-date cancellation refusal, proper cancellation/reschedule,
byte-identical replay.

## Audit findings

Independent GPT source review of diff `973229d..5951830` returned
**FAIL**, identifying that failed Event delegate status was excluded
from the corrected public graph projection, leaving `steps: []` and
`temporal` absent. Report:
`/home/ragdehl/projects/.odyssey-agent-runs/e6-weekend-release-audit-20261022/findings.md`.
A follow-up patch expands the **presentation-only** direct App
flow projection to `COMPLETED`, `PARTIAL`, `FAILED` and
`NEEDS_ATTENTION` if, and only if, real Task/Event interpretation
stages and a real Router provider span exist. No new Planner,
authorization or Writer route is introduced; no synthetic route
without evidence. Six focused regressions cover the two Apps ×
three incomplete statuses; acceptance ledger now anchors them.
Full gate PASS as above.

Pending before promoting this audit patch: independent narrow
re-review and DEV validation of error-state route graphics. Keep
the approved `5951830` active until the new patch is accepted.

## Remaining demo risks and boundaries

- Model latency varies, seen 22–39 seconds; deliberately not being
  optimized during demo hardening.
- Browser used Chromium mobile dimensions, not a real phone.
- Public Cloudflare ingress authentication and availability not
  retested from outside; no claim about external mobile connectivity.
- Not every linguistic mixed-message corner case was sent live, but the
  1856-case cross-surface gate preserves those deterministic contracts.
- All user-facing mutations in this release trial are synthetic.
