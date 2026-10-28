# Product delta independent audit — actual 50k scanner capacity (28 October 2026)

Audit only the new committed source delta since exact ancestor
`52acc73edfdae1c9141edcaa05a3055f30423f27` to the current branch HEAD.
This is a NEW four-role audit for a safety-sensitive Core limit correction,
NOT a retroactive declaration that the old 112-file PR was four-PASS.

Full PR context: on the prior HEAD, Generality PASS, Quality PASS (warning:
matching-SHA DEV acceptance), Testing PASS (same warning), and Performance
BLOCKED because target Pi ARM64 resource evidence and 50,000-note scale proof
were missing. Separate manual host repro created 50,000 synthetic Markdown
notes and proved the failure: storage/repository.py had an inconsistent 30k
version snapshot limit while schema_retrospection.py offered 50k. This is
tracked under GitHub issue #160. The old four reviewers' reports are NOT
inherited or silently assumed valid for the changed code.

This corrective delta shares a single finite 50,000 physical-version path
limit across VaultRepository and the bounded SQLite read-only schema scanner.
It preserves: 20k request-local path cache capacity; 10k candidate E3 journal;
symlink denial, physical freshness and source rechecking, fail-closed excess
capacity, private operational SQLite receipts with canonical Markdown
authority and Core E3/Git gated writes. A compact patched-limit unit test
checks exact-boundary acceptance, >bound rejection and symlink exclusion.
No new provider behavior, E3 write authorization, actor identity, API route or
production deployment was introduced by this fix.

Host measured safe synthetic 50k path at corrected source SHA `5074e3e`:
50,000 regular Markdown files, 1 candidate, 49,999 with property existing,
2,000 pages of 25, 4 read-only job restarts, final SQLite/physical
consistency PASS. Two separate Pi runs: scan 37.90/37.57 sec,
setup+scan before temporary-file cleanup 42.32/42.05 sec, per-process CPU
42.33/42.02 sec, sampled RSS peak 99.36/97.91 MiB, min available host
RAM 1,673.52/1,658.08 MiB, system swap max 1424.11/1424.89 MiB
near starting values 1423.98/1423.66 MiB, temperatures 55.1/54.0 °C.
No 50k Git commit/write and NO p95 or mobile SLA claim. The new opt-in
reproducible probe is `benchmarks/indexing/probe_schema_scan_50k_readonly.py
--run --notes 50000`. Both were low-priority and cleaned /tmp.

Authoritative full Pi host test gate after the code and benchmark change:
2355 Python tests (+7 subtests) and 259 JavaScript PASS, 12 contract groups.
GitHub CI for the new HEAD may still be in progress at review start.
Do not rerun huge benchmarks inside the isolated Codex sandbox; inspect the
real code and host receipt/benchmark contract, identify missing measurements
precisely if they remain necessary. No fabricated p95/swap numbers.

Roles independently decide on the NEW delta:
- Generality: shared finite contract, arbitrary identities and app type
  compatibility, avoid hard-coded corpus-dependent logic.
- Quality: physical source snapshot bound, overflow, symlinks, unknown
  file paths, CAS safety, trusted source, no weakened mutation guard.
- Testing: prove test actually covers the boundary and the reproducible
  50k real Pi read-only scan, distinguish 50k read/scan from writes/latency.
- Performance: evaluate measured Pi CPU, RAM, swap, thermal and duration
  against the scope of *read-only 50k scans*, inspect 50k path enumeration
  and final verifier complexity, resource guards, and avoid unsupported SLA.

Separately from this source-only delta: authentic synthetic
browser→Cloudflare Access→n8n→GPT→Core/E3→Git→browser readback
previously PASS; regular deployed DEV remains at an older SHA, and
matching-SHA DEV deployment/acceptance is still a RELEASE gate.
No model may deploy, merge, modify original DEV or PROD notes, or use
new paid provider calls. Return independent source-backed PASS/FAIL/BLOCKED
in canonical reviewer JSON; distinguish release warnings from blocking
implementation defects. All four roles must run; do not inherit votes.
