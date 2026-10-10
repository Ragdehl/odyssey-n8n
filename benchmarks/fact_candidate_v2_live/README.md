# Router v2 — reviewed four-case synthetic API gate

This separately reviewable source file is **not the previously rejected
inline shell evaluator**. It uses the existing production-shaped Router
request constructor and a committed snapshot, with a separate standalone
offline-by-default CLI. It is intended only for ordinary authorized
execution; a tool safety rejection must not be bypassed by another transport.

## Scope and controls

- Case order: F14, F27, F09, F10 (four synthetic messages only).
- Exactly 4 GPT-6 Luna/low Responses requests; strict Structured Outputs,
  `store=false`, fixed output cap 4096 and OpenAI SDK retries disabled.
- Conservative pre-call total reservation **$0.01181875**, below the user's
  previously authorized **$0.02** total budget. These are bounds, not invoices.
- No Core/Temporal provider calls, no Note writes, no connection to a user vault,
  no model/prompt/schema change or DEV/PROD deployment.
- A fixed request snapshot is verified before any live execution.
- `--live` **and** `ODYSSEY_ROUTER_V2_LIVE_APPROVED=1` must both be present.
  The Python module does not open any secrets file or load shell credentials.
  The authenticated execution environment must be independently authorized.
- Raw model JSON is persisted only for these predefined synthetic sentences
  and is *not* evidence of semantic correctness by itself.

## Safe offline checks (no key, network or provider usage)

```bash
cd /home/ragdehl/projects/odyssey-fact-candidates-v1
/home/ragdehl/projects/odyssey-dev/.venv/bin/python -m benchmarks.fact_candidate_v2_live.run_live
/home/ragdehl/projects/odyssey-dev/.venv/bin/python -m pytest -q tests/benchmarks/test_fact_candidate_v2_live_runner.py
```

Do not set the live flag until the exact command, account, environment,
authorization and limits have been reviewed. A normal approved execution saves
one time-stamped `results/*.json` artifact and prints only summary/usage. No
automatic retries; if any tool explicitly rejects the operation, stop rather
than repackaging it. Compare the observed F14/F27/F09/F10 responses with the
approved source-only contract before deciding whether Router is ready.

The PR must remain Draft until model semantics, independent Core verification
and the inherited historic release tests are resolved.
