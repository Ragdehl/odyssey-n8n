# Conversation front door — C1: contract and bounded errors

Status: **offline-only first implementation** on the development branch. Not active in n8n/DEV, not authorized for live provider calls. Nothing in C1 changes Router/Core/E3 behavior or conversation persistence.

## Prior architecture inventory (reused, not recreated)

- Existing authenticated transcripts: `odyssey_core/local_conversations.py`, segmented actor-scoped store, recent context **up to 16 turns and 4096 bytes**. Current Router independently truncates to **8 turns × 1000 characters** (`odyssey_apps/router.py`).
- Routing ownership/contract: `odyssey_apps/router.py`, `odyssey_runtime/candidate_route_dispatch.py`; real hybrid composition and exact original spans stay unchanged.
- Existing bounded grounded answer model in `workflows/odyssey-online.ts`: reuse it for questions requiring evidence, not an unconstrained Chat answerer.
- E3 conversation reply persistence and idempotence: `odyssey_runtime/composition.py`, `odyssey_core/local_conversations.py`; never add a second transcript.
- Existing structured `clarification` + verified options and `cannot_answer` result: remain canonical. Many n8n reply strings are still fixed; no general error UI override deployed.

## Four modes, deliberately at two different trust boundaries

| Mode | Input | Output | Authority |
| --- | --- | --- | --- |
| `ROUTER` | Exact new message + compact state | Route intent (no source paraphrase) | Existing Router interprets original |
| `CHAT` | Exact new message + compact state | Ask a **future bounded Chat handler** to answer | No Core mutation, no free tools |
| `CONTEXT` | Exact new message + compact state | Request RECENT / HISTORY | Retrieve actor-scoped source turns, **reclassify after retrieval**; no guessed identities |
| `ERROR` | Only verified failed/partial/pending Odyssey result | Human-friendly advice and hint `EXPLAIN/ASK_USER/REVIEW_RETRY` | Diagnostic only; never executes retry |

**A user writing '¿por qué falló?' is a new CHAT/CONTEXT message, not automatically a trusted ERROR.** Error mode is post-execution. An assistant-generated `REVIEW_RETRY` suggestion only proposes review; it is not a retry authorization. Explicit deterministic risk policy will gate any future replay and must check E3 readback/operation ledger, partial writes, idempotency and actor/request identities.

## Implemented C1

`odyssey_runtime/conversation_gateway.py` is a read-only model-facing adapter using existing **gpt-6-luna**, low reasoning, `store=false` and strict Responses schemas. The first request returns only `mode` and `context_scope`. It supplies the exact message plus **tiny prior continuity hints** (topic hint, pending clarification, last status) rather than 30 days of chat. Model failure and invalid JSON fail closed.

`read_recent_continuity` reuses the real `LocalConversationStore.recent_context`, excluding the current request, supplied via the **existing trusted actor-bound resolver**. `HISTORY` explicitly fails pending the next stage rather than quietly substituting unrelated turns or summaries.

For `ERROR`, the caller must build `VerifiedFailure` from existing verified request results: status, reason code and **explicit canonical write evidence (`0`, positive count or `None` meaning unknown; never default `0`)**. Luna receives a small whitelist, **not a raw execution graph, prompt, Markdown or authentication material**. After the first independent audit identified risks of fabricated write claims, the provider schema was narrowed further: the model chooses **only a finite `guidance_kind` plus a non-executing recovery hint**. Odyssey renders trusted, vetted user-language templates and a deterministic status prefix; unknown write evidence is explicitly labeled as unknown. No free-form model message can claim that nothing was saved or silently recommend an executable retry. The model does not receive `request_id` and cannot choose a note, submit a new request or set `retry_authorized`. More natural error explanations require a separately reviewed evidence-grounded response contract.

Tests: `tests/runtime/test_conversation_gateway.py`, registered in the permanent cross-surface gate. Fake SDK-shaped provider replies, strict parser rejects, no fabricated routes, actor-isolated transcript reuse, distinct post-error input, partial/unknown write status and no auto-repeat. **C1 final offline gate: 1,950 Python tests + 184 JavaScript tests PASS, 12 groups**. The first independent audit found arbitrary error prose and implicit zero writes; both corrected. No real-model tests or DEV adoption asserted.

## Next functional adoption gates (not yet implemented)

1. **C2 — context gateway**: introduce a small, typed `active_topic`/pending-clarification state derived from **verified transcript** (not a model-invented identity). Load exact recent turns on `CONTEXT`; for `HISTORY`, develop bounded actor-scoped 30-day retrieval from the already stored transcript, topic/week summaries referencing immutable original messages. Time filters, deletion, expiry and integrity tests needed; summaries are indexes, never canonical facts.
2. **C3 — Chat/help branch**: create the bounded Chat response service. Reuse existing grounded answerer for notes; load [user help](../product/odyssey-chat-help.md) **only** for explicit Odyssey-help questions, with feature availability controlled by deployed code, not stale docs. Preserve actor context, transcript idempotency and reply schema. Clarification replies must resume the original request rather than be stored as unrelated facts.
3. **C4 — error integration**: map trustworthy structured `product_reason/clarification_code` and E3 physical write receipts into `VerifiedFailure`; render advice via existing assistant result pipeline with safe deterministic fallback on provider failure. Do not rewrite existing E3 error policy; no speculative root-cause claims and no automatic retries. A separate reviewed recovery policy may later allow a **single** bounded replay only after evidence proves zero/known writes.
4. **C5 — authorized live/visual acceptance**: invoke the `odyssey-llm-stage` + `odyssey-live-provider` workflows, test real Luna classification on saving/conversing/mixed and continuity cases, check mode accuracy and false suppression of writes, fail-closed errors, browser/n8n end-to-end and trace. Run full cross-surface regression before adopting. Measure latency/cost; never equate a fake provider PASS to actual conversational quality.

Do not increase the Router's context length casually. Its current 8-turn limit is for routing-only classification; wider context should be carefully retrieved by Chat/continuity, scoped to trusted actor and exact source, and delivered as **hypothesis** rather than silently incorporated into a user message.
