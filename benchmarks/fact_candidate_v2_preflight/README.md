# Router fact candidates v2 — offline preflight only

This folder is **not a live-model runner**. Its Python module imports only Odyssey's existing request constructors and local fake responses. It cannot import the OpenAI SDK, load a key, use the network, mutate notes, or deploy anything. It prints only non-sensitive request metadata and static input/output pricing estimates.

Run from the isolated feature branch:

```bash
/home/ragdehl/projects/odyssey-dev/.venv/bin/python -m benchmarks.fact_candidate_v2_preflight.check
/home/ragdehl/projects/odyssey-dev/.venv/bin/python -m pytest -q tests/benchmarks/test_fact_candidate_v2_preflight.py
```

The 2026-10-10 pinned price snapshot and an intentionally large bound of `2 * serialized request bytes + 200` tokens for **all fields including the system prompt and JSON Schema**, plus the model's maximum output tokens, are used. Where present, the higher input/cache-write rate is used. This is a conservative **planning envelope, not a predicted invoice** and not a proof of SDK token accounting. Do not weaken these assumptions merely to fit a desired budget.

Nine proposed calls (4 Router, 2 Temporal, 2 Luna Core, 1 attribution) have a static worst-case envelope around **USD 0.0848571**, exceeding the user's USD 0.02 authorization. A staged **six-call Router + Temporal** evaluation would have a static upper envelope of **USD 0.013495**, covering F14, F27, F09, F10. This offline report **does not authorize or implement that live execution**.

No existing reviewed runner covers these exact v2 candidates under the authorized ceiling. The attempted creation of a separate live runner through a large remote shell operation was explicitly **blocked by the platform safety controls**. Do not split/repackage or reroute the rejected operation to bypass that block. Before any live calls, the platform must permit an ordinary reviewed procedure with pre-call budget reservation, no SDK retries, `store=false`, synthetic sources, and the existing sanctioned transient `systemd --user` secret transport. Keep the protected DEV/PROD paths untouched. See [GitHub issue #151](https://github.com/Ragdehl/odyssey-n8n/issues/151).
