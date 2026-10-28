# Scoped four-role independent review: bounded multi-journal campaigns

Review the committed feature delta from ancestor 033c323d969e6dffb7314daf45af34d267fb5a30 (resumable 50k scanner) to the immutable source HEAD of PR #156. This is an INCREMENTAL scope, not retrospective certification of the entire 1MB+ PR. Explicitly distinguish the scope.

Odyssey is local-first mobile-targeted. Markdown is canonical. Only Core/E3+Git authorizes edits, using exact source facts, CAS, actor, readback and per-note undo. A human approves the optional-property schema, and Notes schema_backfill validates that approval and schema revision on each stage/status/advance. No model, SQLite, browser or n8n can grant write permission.

Inspect changed source: odyssey_runtime/schema_backfill_jobs.py bounded staging and full-vault stable identity fingerprint, odyssey_runtime/schema_backfill_campaign.py signed HMAC parent over multiple 1k-row child V1 journals, odyssey_runtime/composition.py public routing, tests/runtime/test_schema_backfill_campaign.py, tests/runtime/test_schema_backfill_notes_vertical.py, benchmark, roadmap. Read necessary contracts in odyssey_core/schema_retrospection.py, odyssey_core/schema_auto_backfill.py, odyssey_core/git_history.py and user_schema_registry.py. Existing V1 journals must remain supported.

GENERALITY: test cursor and identity behavior for arbitrary type/path ordering, changing property eligibility, skipped/deferred values, multiple Apps and 50k vault. Identify dropped or duplicated candidates and whether full-vault identity proof is stable across segments.

QUALITY: adversarial HMAC tamper, cross-actor and schema isolation, OS files/symlinks, concurrency, lock ordering, restart before/after child publish, signed parent frontier, and after Git commit. Look for missing/forged journal behavior, invisible skipped notes, ambiguous writes or unchecked transition. Reproduce defects and cite exact lines.

TESTING: assess synthetic coverage and attack edge cases not actually exercised by tests. Be precise about cases: 6 notes/3 child journals with separate Git commits; 11k eligible source files/3 real E3 commits across 2 children; crash reconciliation and Notes API actor tests. Isolated Chromium+n8n+Core/E3 pass is not live deployed DEV/GPT/Access, nor 11k writes.

PERFORMANCE: N global Markdown inventory reads at each child stage, ~1k candidates per journal and N-verifying CAS per write. Measured Pi fixture: 11k eligible, first stage 3.73s, 3 writes 11.17s, peak RSS 68.5MiB. Explain scaling and feasible safe bounded improvements, without invented p95 or mobile battery numbers.

Reported local full cross-surface PASS 2312 Python (161 files) + 252 JS on prior HEAD; CI and isolated Chromium PASS. New source SHA must be verified. DEV still deployed 4e721a0, backfill/assistant off. No paid GPT, authenticated external Cloudflare acceptance, native Android worker, or 10k actual writes. Four-role independent source findings are NOT approval to merge/deploy.

Review READ ONLY, do not modify any code, PROD, personal notes, credentials, external services or deployments. PASS with explicit evidence gaps is allowed; FAIL/BLOCKED must include actionable file:line and reproduction.
