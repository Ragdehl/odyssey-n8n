# UI-0 — durable main conversation and natural continuity

Status: **IMPLEMENTATION IN PROGRESS — simplified architecture re-challenge: PROCEED**

## Objective

Make Odyssey's one ordinary chat durable across reopen while preserving natural short follow-ups.
Odyssey is a personal memory based on local notes, consultable and modifiable through natural
language; it is not a general purpose messaging product. Conversation exists to make use of that
memory natural, not to become competing personal knowledge.

```text
durable actor-scoped main transcript
            |
current request + bounded recent visible turns
            |
            v
     one Luna-first planner pass
            |
            v
validated intent / referent -> canonical note retrieval or mutation
```

## Accepted product and storage contract

- The browser opens one persistent main conversation for the validated Odyssey actor. Reopen and
  reload restore its visible chronological turns; the user does not select or manage chats.
- `main` is a stable internal `conversation_id`. The durable repository retains its generic safe
  record format internally, but UI-0 exposes neither a conversation list nor new/open actions.
- Records are human-readable validated JSON under
  `ODYSSEY_STATE_ROOT/conversations/<sha256(internal-actor)>/main.json`, outside the vault and all
  note indexes. A validated internal actor owns every record; no untrusted external subject is a
  path component.
- Records contain visible user/final Odyssey turns, timestamps, request correlation and bounded
  outcome status only. They never contain prompts, hidden reasoning, raw provider data,
  credentials, or canonical-note copies.
- The existing `request_id` plus role makes durable turn writes idempotent. A user turn is recorded
  before Core execution and the final visible Odyssey turn after the product result is known.
  Durable-state failure fails closed rather than claiming a saved transcript.

## Recent-context and authority boundary

Every UI-0 request uses the existing Luna-first planner once. Before that one call, Core supplies
complete most-recent visible turns from the active main record, excluding the current `request_id`:

- initial resource bound: **4,096 UTF-8 bytes** and **16 complete turns**;
- selection is reverse-recency until either ceiling, then restored to chronological order;
- no summary call, history search, semantic index, or hidden transcript is used.

The byte ceiling is a deterministic safety budget rather than a claim that a fixed number of turns
is semantically sufficient. It is deliberately modest for ordinary mobile continuity. The focused
UI-0 evidence saw roughly 12k input tokens for each planner call: adding at most about 1k tokens
to one call is materially cheaper and simpler than a `CONTEXT_NEEDED` second full planner pass.

Conversation text is inserted **only into the planner prompt** as non-authoritative continuity
evidence. It may identify what person or interaction words such as “ella”, “allí”, or “entonces”
refer to. It must not become a retrieval filter, asserted current fact, write target, or mutation
fact. The validated plan alone crosses into canonical retrieval/mutation; current canonical Markdown
remains the authority for present facts. If the window leaves a referent or write meaning ambiguous,
the planner clarifies rather than guessing. Explicit prior user text may be reused only through the
ordinary validated write contract; prior assistant wording is never a fact or mutation target.

## Acceptance criteria

1. One stable actor-scoped `main` conversation survives reload/restart and restores visible turns.
2. User and final Odyssey turns retain timestamps/request correlation and are idempotent on retry.
3. State records do not enter canonical note scans, embeddings, retrieval, or personal knowledge.
4. A self-contained request remains one planner call even with unrelated recent chat.
5. An unambiguous immediate omitted-referent follow-up resolves in that one pass using the bounded
   window, then retrieves current facts only from canonical synthetic notes.
6. Old conversation wording cannot become a current-fact filter or override current canonical data.
7. Two plausible referents and ambiguous follow-up writes fail closed to clarification.
8. Only the bounded complete-turn window reaches the planner; no full transcript or provider data
   reaches it.
9. The mobile surface remains one simple chat: reopen, see prior turns, continue; no chat-management
   mental model is required.
10. Isolated DEV deterministic, focused live, and mobile evidence use synthetic data only and leave
    production untouched.

## Explicitly deferred

- multiple-chat management, topic splitting, threads, and app-specific chats;
- historical conversation search (“what did I say on …?”), conversation embeddings, and cross-chat
  retrieval;
- generated summaries or summary hierarchies;
- retention/export/deletion policy and general assistant memory;
- Notes, Tasks, Projects, and unrelated UI work.

Raw transcript timestamps and stable request correlation deliberately leave future historical
features possible without changing current authority boundaries.

## Re-challenge checkpoint

The earlier UI-0 design implemented generic durable records, user-facing multiple chats, and a
planner `CONTEXT_NEEDED`/bounded-second-pass experiment. Two focused live gates showed that the
second pass added a full additional Luna prompt while the model did not reliably choose the new
intermediate outcome. The re-challenge found that this complexity was not required for the approved
personal-memory product requirement. UI-0 therefore removes the UI-specific structured outcome,
Luna teaching, active-conversation selection, and second planner pass rather than preserving dormant
machinery. The durable actor-scoped record/idempotency substrate is retained because it directly
serves persistent main-chat continuity and future compatibility.

No further product, security, or authority decision is required for this bounded simplification.
