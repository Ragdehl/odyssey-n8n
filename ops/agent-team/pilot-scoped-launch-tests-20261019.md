# Agent team acceptance pilot — isolated builder and safe environment tests

Goal: Codex Builder independently adds focused, deterministic regression tests for the ALREADY-INTEGRATED safe-native sandbox behavior in scripts/odyssey_agent_cycle.py. Existing product code must be unchanged.

Scope and acceptance:
1. Edit ONLY tests/runtime/test_agent_cycle_supervisor.py. Make TWO or THREE meaningful pytest test cases for the current code:
   - The BUILDER (not just a read-only reviewer) is refused BEFORE Popen if probe_native_profile fails, and token ledger stays untouched.
   - Successful mocked model launch uses a POSITIVE environment allowlist so injected secrets or unrelated variables (OPENAI_API_KEY, N8N_TOKEN, CLOUDFLARE_API_TOKEN, AWS_ACCESS_KEY_ID, CUSTOM_RANDOM_ENV) cannot reach the process. Confirm that HOME/PATH survive and that the model's scoped permission override and matching receipt exist. Use monkeypatch and fake Popen without real model/provider calls.
   - Optional: tests prevent CLI launch if the preflight raises another known safe exception (e.g., subprocess.TimeoutExpired).
2. Base these tests on existing working fake-Codex subprocess patterns in test_agent_cycle_supervisor.py; do not invent fallback security claims, and do not read any real secrets. Tests should pass using the real supervisor API and in-memory test fixtures.
3. Do NOT modify scripts/odyssey_agent_cycle.py or any other source, configs, docs, policy, benchmarks, or preexisting test expectations. No Git commit is necessary. Do not touch DEV, PROD, /data, secrets, Cloudflare, container services, model credentials, or external network.
4. Run ONLY pytest -q tests/runtime/test_agent_cycle_supervisor.py and Ruff for that test file inside the restricted worktree; if any test cannot run in Codex's networkless sandbox, report precisely rather than disabling it. The supervisor will run the authoritative complete Python+JS gate outside Codex.
5. Do not broaden the task, refactor production, or add redundant test helpers. Aim for minimum diff and clear assertions. If all checks pass, finish with a compact factual change summary.

This is normal-risk INTERNAL TOOLING acceptance (not an Odyssey product release). Architecture/Generality and Security/Quality auditors must independently review the code. No auto-merge, deploy, push, or user data access.
