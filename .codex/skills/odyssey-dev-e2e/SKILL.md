---
name: odyssey-dev-e2e
description: Deploy, test or recover Odyssey DEV, including browser→n8n→GPT→Core/E3→Markdown→Notes/Calendar and UI graph. Use for releases, regression investigation and demo readiness.
---

# Odyssey DEV E2E and safe adoption

1. Run `odyssey-start-work` and context doctor. Distinguish working source SHA, immutable target commit, DEV checkout, `/data/odyssey-dev/runtime/deployed-commit`, runtime/n8n HTTP, Git remote and PROD. Detect another deployment/job **before** mutation.
2. Evidence pyramid: focused tests → `python scripts/odyssey_cross_surface_gate.py`, acceptance ledger, Ruff → isolated real-provider E2E if model-facing → actual Chromium/browser clicks → Markdown + UI readback. Do not equate Python green, browser-only fake provider and real GPT E2E.
3. Cover relevant actions: create/update/query/cancel Events; Tasks/subtasks/Work Sessions; calendar month/day/1/3/7 views; Notes/backlinks; route diagram, donut, stage timings; idempotence, stale/ambiguous refusal and reload persistence.
4. DEV writes use synthetic names/data with bounded authorization. PROD/private vault is out of scope. Before deploying a clean **pinned full SHA**, retain verified backups and last-good rollback; use tracked `scripts/odyssey-dev` and `docs/architecture/phase-21-development-isolation.md`. Do not race or interrupt n8n import or run overlapping deployments.
5. If import/readback fails, separate n8n startup, runtime, provider semantics, E3 writer, UI and timing/checkout races. A test running during another deploy is inconclusive. Recover the last complete known-good DEV state; verify matching marker, checkout, services and vault.
6. Document exact tested SHA, actual deployed marker, tests and authenticated browser evidence, backups, limitations and errors. Never claim universal regression-free behavior.

For paid provider evidence first read `odyssey-live-provider`. For status and tests see `docs/architecture/functional-roadmap.md`, `docs/architecture/testing.md` and `scripts/odyssey_dev_browser_readonly.cjs`.
