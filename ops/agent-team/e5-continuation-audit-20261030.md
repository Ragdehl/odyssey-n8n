# E5 selected-source continuation — independent integration audit, 30 October 2026

Review the pinned PR #161 incremental changes after be7577e only. User explicitly
authorized full four-role Codex audits and sufficient local reported-token budget.
The **whole PR** is larger and has historic partial review; do not mistake this
incremental four-role review for four PASS on all 680 KB of PR code.

## Existing behavior and tested scope
- The October 10 F14/F27 literal old pilot **already** linked a Luis fact to
  a Day note in synthetic Core/E3; it is quarantined and not production-ready.
  Do not count this as newly invented functionality.
- The ordinary Core/E3 Writer, pending actor-local clarification, readback
  validator and LocalDeliveryResultStore are reused.
- New generic independent semantic review prompt: real GPT-5.6 Luna/low
  16/16 scoped synthetic corpus (5 positives, 11 negative; ES/FR/EN), exact
  prompt SHA e27c13afbff564736fe6f32f56589c0dc6ed02ff2679d27042f4f66fc89fa2c9.
  Earlier v1 11/16 and v2 15/16 fail were addressed by exact echo of proposed
  text and explicit typed fact kind. Evidence in docs and script.
- New RuntimeComposition opt-in continuation callback is disabled by default.
  Only isolated DEV with existing light source path may enable the flag.
- Synthetic product tests show clarify -> injected reviewed-plan callback ->
  original Core/E3 -> physical Markdown readback -> immutable delivery receipt
  -> same-ID replay with zero duplicate writes. Failures before claim are
  distinct from crash after claim. Old pending state stays selected.
- **CRITICAL OPEN BLOCKER**: two independent genuine planner-only provider
  probes both FAIL BEFORE WRITES: ordinary Core Planner produced
  "KnowledgeUnit fact reference marker is out of range", experimental Luna
  planner "Luna semantic WRITE failed local compilation", when presented
  with selected pronoun identity hint. The reviewer 16/16 does not prove
  the actual product's Planner can return any accepted plan.
  The feature flag MUST stay OFF, product NOT ready, no real browser acceptance.
- DEV still pinned 4ba8bb8; PR head not deployed; real DEV/PROD/personal vault
  must not be read or touched by the reviewers.

## Independent review expectations
- Generality: no example-based workarounds or second Planner/Writer/DB.
  Evaluate chosen identity hint and original date; type/shape compatibility
  with the standard Core Planner; actor/conversation scoping.
- Quality: strict no-double-write claim/replay, exact E3 guard/selection and
  source/digest freshness. Whether product callback can claim completion before
  verifying all physical evidence, crash/restart, multi-user and prewrite
  versus postwrite errors. Verify feature OFF by default.
- Testing: distinguish 16 live reviewer calls from two failed Planner calls,
  synthetic product tests vs authenticated Chromium+n8n E2E and real model
  integration. Find missing negative tests and gaps in source/clock handling.
- Performance: check linear readback scan limits, repeated OpenAI calls,
  when locked Product.execute calls held, partial reconstruction costs and
  indexes. Do not invent bench measurements.
- Provide specific exact file/function defects and safe targeted repairs.
  Set BLOCKED/FAIL honestly for missing real planner or DEV browser evidence.
  Do not modify code, personal notes, Cloudflare, DEV, PROD or n8n.
  Four roles do not authorize merge/deploy.
