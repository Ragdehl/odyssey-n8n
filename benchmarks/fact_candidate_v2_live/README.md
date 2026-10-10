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

## Proposed Router prompt revision v2 (isolated, not active)

GPT-6's first real F09/F10/F14/F27 gate exposed a semantic mistake
(F09 two separate residences grouped as a single relationship) and
Core-blocking source role errors (F14/F27 date/reference/participant scopes).
A **versioned v2 prompt extension** supplements every existing v1 instruction
without changing the JSON schema, normal Router runtime, canonical NoteSchema
or Core, and is selected only with `prompt_revision="v2"` on this inactive
candidate adapter. It clarifies general product distinctions for independent
properties, mutual relationships, coherent shared encounters, explicit
sequence, lexical `date` vs `time`, exact `reference` evidence and ordinary
future activities. It does not add local keyword heuristics, rewrite spans,
guess identities, or grant write authority.

The four revised request envelopes are independently frozen in
`prompt_v2_requests.json`. The normal offline default continues to use v1
for historical reproducibility. To inspect v2 **without any provider use**:

```bash
python -m benchmarks.fact_candidate_v2_live.run_live --prompt-v2
python -m pytest -q tests/benchmarks/test_fact_candidate_v2_live_runner.py
```

The live command (only after normal approved per-call budget review) is
`python -m benchmarks.fact_candidate_v2_live.run_live --prompt-v2 --live`
inside the established transient `systemd --user` service with the fixed
EnvironmentFile, explicit authorized flag and no shell credential loading.
It makes **exactly four** calls. The revised conservative four-call reservation
is `$0.01379775`; the first observed v1 run cost is `$0.0010009`
estimated from saved token counts and pinned rates, giving a combined estimated
prior spend + *fully reserved new upper envelope* of about `$0.01480`,
below the previously approved `$0.02` total. This is not an invoice and
the final comparison must still include an independent semantic review.
