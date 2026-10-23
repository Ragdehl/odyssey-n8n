# Conversation C2 — actor-scoped continuity and real prompt evaluation (23 October 2026)

**State: development-only, not deployed or connected to the user-facing chat.**
C1's initial Luna classifier and C2's follow-up classifier have **separate** model contracts.
The existing Router/Core/E3 are unchanged and retain all write authority.

## What has been added

- `odyssey_runtime/conversation_continuity.py` retrieves prior exact turn text,
  original request identifiers and timestamps from the existing
  `LocalConversationStore` **already resolved for the authenticated actor**.
- `CONTEXT RECENT` reuses the existing 16-turn / 4096-byte bounded recent
  context. `CONTEXT HISTORY` pages backward through the existing durable
  transcript up to **30 days**, 48 turns, 12 KiB and 8 pages. It excludes the
  current request, future timestamps and older messages. This is NOT a 30-day
  conversation summary, semantic search or unrestricted month-by-month memory.
- `ContextHandoff` preserves the untouched user message and source provenance.
  `as_routing_context()` limits the original context to the **existing eight
  Router turn maximum**; it adds hypotheses, never canonical identities.
- `OpenAIConversationGateway.classify_after_context` performs a second and
  **final** strict Luna decision using actual previous turns, without modifying
  the message. A second `CONTEXT` is an instruction to **ask for clarification**,
  not to make another call or guess participants.
- Controlled gates:
  `scripts/odyssey_chat_live_prompt_gate.py` for entry classification and
  `scripts/odyssey_chat_live_context_gate.py` for follow-up classification.
  Both require `ODYSSEY_CHAT_LIVE_APPROVED=1` and the protected user-systemd
  EnvironmentFile; no production vault, browser or n8n operations.

## Fresh model evidence: do not confuse schema correctness with intent correctness

**First classifier** (`gpt-6-luna`, low reasoning, strict JSON; synthetic cases):
- V1: 9/12 correct; missed work-session, old-conversation and mixed-message intents.
- V2: 11/12; missed an elliptical multi-message continuation.
- V3: **12/12**, prompt/schema hash `364485af6b2a857e`, log
  `/tmp/odyssey-chat-c1-real-model-matrix-v3-20261023.log`.
- A small one-shot matrix confirms these particular decisions, **not** robust
  performance across phrasings or repeated provider calls. Do not promote
  the feature based on that 12/12 alone.

**After-context classifier** (separate second prompt):
- V1: 2/3; an unsupported collective reference was routed prematurely.
- V2: 2/3; a supported Bruno continuation was instead conservatively
  classified CONTEXT. Logs:
  `/tmp/odyssey-chat-c2-real-context-20261023.log` and
  `/tmp/odyssey-chat-c2-real-context-v2-20261023.log`.
- **Not accepted** for actual user-facing decisions. The tradeoff indicates
  that merely strengthening prompt warnings does not resolve ambiguity.
  Next work must define a general contract separating (a) intent to save,
  (b) confidence that the original's referenced participants can be supported
  by trustworthy context, and (c) mandatory Core-level identity validation.
  An unsupported group must never become fabricated write targets, but
  an otherwise valid save intention should not be silently dropped.

## Acceptance before activating C2

- Define *a single* accepted, non-looping after-context semantic contract,
  a larger real-provider matrix with repeated ambiguous/supported/contradictory
  continuations, and stable negative gates; then prove Router receives the
  **original unchanged** and actor-authenticated evidence.
- Verify pending clarification resume and two-stage answers, and guard against
  mixed save+chat messages being suppressed. Typed N:M/identity/Core/E3
  authority remains unchanged.
- Historical summarization by week/month, topic relevance and feature-help
  branches are **not implemented** here. They require separate provenance
  and scoped tests. Do not silently use generic LLM background memory.
- Full offline cross-surface and real browser→n8n→GPT→Core/E3→Markdown→UI
  synthetic end-to-end tests and explicit deployment authorization are required
  before C2 becomes user-visible.

This report intentionally records the 2/3 real result rather than relaxing
expected outcomes or claiming an accepted prompt.


## Final offline receipt for this checkpoint

- Full cross-surface regression after the corrected historical reader: **1,960 Python tests, 184 JavaScript tests, 12 contract groups PASS**; Ruff check/format and docs guard PASS. Evidence `/tmp/odyssey-chat-c2-final-after-review-20261023.log`.
- A scoped independent reviewer found two genuine retrieval problems: out-of-order timestamps prematurely stopped history paging, and identical text in different turns could lead to incorrect request-ID provenance. Both were corrected by skipping out-of-window turns while paginating (bounded 8 pages) and reading **original stored IDs directly** instead of reconstructing IDs from role/text equality.
- New regression tests cover out-of-order append timestamps and duplicate text with an excluded future timestamp. The focused follow-up review of these two repairs returned **PASS by inspection**, separately from the actual local tests.
- The real after-context classifier remains **BLOCKED (2/3)**; this does **not** authorize a Chat route switch or error recovery on DEV. No changes were made to real user data or production, and no active deployment was performed.
