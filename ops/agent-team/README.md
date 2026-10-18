# Odyssey Agent Team — Pilot (18 Oct 2026)

A supervised, bounded **development workflow**, not a new Odyssey user-facing App or alternate Core, Writer, Graph or database.

## Owner and roles

Supervisor: `scripts/odyssey_agent_cycle.py` is a deterministic state machine that checks gates, records status/receipts, bounds attempts and protects DEV/PROD. Five Codex specialists run *one at a time* in a fresh `agent/<job>` Git worktree:
1. Builder — implementation and focused tests (only editing specialist).
2. Generality — reusable Core contracts, arbitrary future App audit.
3. Quality — security, E2/E3, canonical Writer, maintainability.
4. Testing — adversarial, full-source and genuine end-to-end evidence.
5. Performance — timed real Pi runs, RAM/CPU/swap and scaling evidence.

Reviewers are independent sessions with read-only sandbox and strict machine-readable results. The Builder receives all their findings and, if no essential environmental gate blocks work, may repair and repeat. Never more than three iterations or one Codex process concurrently.

## Status and commands (on the Raspberry Pi)

```bash
cd /home/ragdehl/projects/odyssey-e3-mutation
python3 scripts/odyssey_agent_cycle.py doctor
python3 scripts/odyssey_agent_cycle.py plan --spec ops/agent-team/pilot-p4.md --job p4-agents-pilot-20261018
python3 scripts/odyssey_agent_cycle.py status --job p4-agents-pilot-20261018
# Do NOT execute unsupervised until sandbox and real browser gate are evaluated:
python3 scripts/odyssey_agent_cycle.py run --job p4-agents-pilot-20261018 --max-rounds 2 --live
python3 scripts/odyssey_agent_cycle.py stop --job p4-agents-pilot-20261018
```

The `plan` operation is a **safe dry run**: it saves the brief and Git baseline but launches no Codex session and creates no extra worktree. `run --live` is explicit and creates a new local Git branch/worktree. The persistent report is `../.odyssey-agent-runs/<job>/status.json` with each round's logs and reviewer JSON (0700 directory). While running, the supervisor checks a STOP marker and real `/proc/meminfo` every two seconds; memory under 650 MiB cancels the Codex process. Time limit 20 minutes per specialist, maximum three repair cycles, test gate timeout four minutes each. On restart, the same job cannot be launched again silently. There is no auto-merge, auto-push or deployment.

The full offline gate is `scripts/odyssey_cross_surface_gate.py`, plus accepted-contract ledger and Ruff checks, and two independent model-sensitive E2/E3/QA and performance audits. **Offline green does not mean DEV-user-ready.** Even with all reviewers passing, it reports `reviewed_browser_gate_pending` until a real authenticated browser→n8n→GPT→Writer→Markdown→browser gate is integrated. A reviewer with missing necessary evidence returns `blocked`, stopping the repair loop instead of wasting further tokens.

## Current pilot boundaries

- Local model sessions run under the user's existing ChatGPT Codex login. CLI is `0.162.1`, Pi ARM64 4 GiB, 2 GiB swap. The supervisor ignores local Codex MCP configuration, filters environment secrets, restricts edits to an isolated workspace sandbox, and does not expose DEV/PROD volumes deliberately.
- **Not a formal OS/container isolation boundary.** The same Linux account owns personal files and credentials. For wholly unattended agents with arbitrary shell access, move the runner to a dedicated restricted account/container with no mount of `/data/odyssey`, Cloudflare tunnel credentials or deploy permissions. Do not interpret prompt prohibitions as security controls.
- The real-browser automated runner and mobile push notification channel are not connected yet. Codex on ChatGPT mobile supports remote/cloud task control, but Raspberry Pi host availability and the requested notification UX must be verified on this actual host. A local JSON report does not automatically message this chat. Options: Codex Remote, GitHub PR checks/notifications, or a separate read-only n8n notification bridge, subject to user preferences.
- No generic user-created App is executed untrusted here. Odyssey's eventual Lego/contracts model requires declarative capabilities, schema validation, data permissions, compositional contract tests, and isolated evaluation of generated Apps; running user-provided code with normal Core privileges would not be safe. We do not redesign E1–E6 while delivering this pilot.
- P4 currently has historical frozen benchmark failures: the full suite is NOT a green release gate unless only independently documented historical cases fail. Never update price hashes merely to greenwash the run.

## Next adoption gate

Pilot with ONE bounded, READ-ONLY architecture/generalization review. Verify actual Codex CLI JSON output, cancellation, Git worktree isolation, and resource reporting. Then run a tiny expendable feature through implementer→reviewers on a dedicated worktree. Integrate browser E2E and notifications before running substantial unattended loops. **Do not start the complete live loop without these proofs.**
