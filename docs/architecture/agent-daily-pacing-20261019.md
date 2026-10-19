# Odyssey — daily pacing for autonomous Codex agents (19 October 2026)

## What has actually been implemented

`scripts/odyssey_agent_pacing.py` is a **conservative local usage estimator**. It counts CLI-reported token usage from **all jobs** in `../.odyssey-agent-runs/<job>/status.json`, grouped by a session's end date in the `Europe/Paris` timezone. New sessions store `ended_at`. Historical job receipts that lack `ended_at` are conservatively assigned to the job's `updated_at` or `created_at` date; records with no way to determine a date fail closed.

The calculation requires the operator to supply an explicit **weekly reported-token PROXY**, which is **not** ChatGPT's allowance. Daily cap = `floor(weekly_reported_proxy * (100-reserve_percent) / 700)`; default reserve is 20%. The value must support a minimum 40,000-token session reservation. For example, **a hypothetical** weekly CLI-reported proxy of 700,000 with 20% reserve yields 80,000 tokens per local day. This is a policy example only; no account limit or subscription allowance is inferred. A single model call can exceed this threshold because Codex CLI reported-token telemetry is usually finalized only on exit.

Commands:

```bash
# Read-only; no model call, no changes to current policy:
python3 scripts/odyssey_agent_cycle.py pace

# Explicit operator calibration using an example, NOT the user's weekly allowance:
python3 scripts/odyssey_agent_cycle.py pace --weekly-reported-proxy 700000 --reserve-percent 20

# View status, model routing and reviewer reservation for an existing job:
python3 scripts/odyssey_agent_cycle.py route --job <job>

# Only when pacing is configured and a feature has been planned:
python3 scripts/odyssey_agent_cycle.py run --job <job> --max-rounds 2 --live
```

A run via the official CLI `run --live` **refuses to begin** without a configured policy. For configured installations, `codex()` checks the global daily remaining reported-token headroom before EACH individual model launch. `status`, `doctor`, `pace`, and model-free route inspections are read-only. Policy files have 0600 permissions under the local 0700 private state directory. The existing supervisor lock still serializes actual jobs; no new scheduler or agent platform is introduced.

### Current historical readback

The first real status probe **on October 19, 2026** found **153,831 reported tokens** attributable to today's earlier scoped autonomy job and did not mistakenly report zero. The pacing policy has **NOT** been configured, because the actual weekly ChatGPT account quota and its conversion to CLI-reported tokens are unknown.

Tests in `tests/runtime/test_agent_daily_pacing.py` verify all-jobs accounting, daily reset and timezone conversion, inclusion of legacy sessions, refusal of corrupt or symlinked policy and unattributable records, explicit configuration, actual CLI refusal without configuration, prelaunch refusal when a DIFFERENT job has consumed the day's allocation, and timestamped session receipts. They run without network/model calls; included in the official cross-surface gate.

## Critical limitations before unattended multi-day product autonomy

1. **Not an OpenAI allowance meter.** Work, Codex Cloud and other clients may consume the same included allowance without reporting sessions to Odyssey. Actual five-hour and weekly limits, reset times and current remaining quota are shown in ChatGPT Settings → Usage / Codex `/status`; Odyssey has not been given a supported authenticated programmatic usage feed. The reported-token proxy is a secondary guard, **not** a guarantee against using up the subscription allowance.
2. **No true hard intrasesion token ceiling.** One Codex model call can overrun remaining tokens. Existing timeout, RAM, STOP and model headroom checks still apply. Unaccounted interrupted/in-flight model usage requires more durable reservation/reconciliation safeguards.
3. **No resume-on-next-day checkpoint.** The existing supervisor can block on daily headroom between sessions, but `run()` does not yet resume a partially completed round from the exact audited point. This is the next REQUIRED step for a genuinely autonomous multi-day job. **Do not promise scheduled next-day continuation**.
4. **Full product validation not complete.** All product features still require four independent specialists and a genuine authenticated browser→n8n→live GPT→Writer→Markdown→Notes/graph after reload on a synthetic DEV identity. Current offline/synthetic E2E gates do not authorize DEV or PROD deployment.
5. **Human-visible completion reporting** is still local JSON evidence rather than automatic notifications to this ChatGPT conversation. Neither live execution nor deployment is scheduled.
6. **Budget quote:** default 110,000 CLI-reported tokens cannot reserve the minimum of 40,000 Builder + 205,000 product specialist reviews. Per-feature planning needs an explicit larger cap and credible daily pacing, or the job blocks before launching the Builder. Reservations aren't hard spend ceilings.

In particular, avoid converting 153,831 CLI-reported tokens into a claim of 153,831 tokens from a fixed Plus weekly allowance. No such conversion is supported.
