# UI-0 — durable conversations and resume

Status: **CONTRACT PROPOSED — architecture challenge required before implementation**

## Objective

Make Odyssey behave like a real durable conversation product: conversations survive page/app reopen, can be listed and resumed by stable identity, and resumed conversations can support natural immediate follow-ups without turning chat text into canonical personal knowledge.

UI-0 should establish the smallest reusable conversation substrate needed by later Notes/app work while preserving Odyssey's current authority boundaries and simplicity principle.

```text
user opens Odyssey
      |
      +--> new conversation
      |
      `--> reopen existing conversation
                 |
                 v
       durable visible turns
                 |
                 v
       same conversation_id
                 |
                 +--> self-contained request -> ordinary path
                 |
                 `--> context-dependent request
                          -> bounded active-conversation evidence
                          -> same planner second pass
```

## Product contract

The user should not have to manage context manually.

- Odyssey supports multiple durable conversations rather than one global transcript.
- Each conversation has a stable `conversation_id` and is scoped to the authenticated Odyssey user/actor.
- Closing/reopening the browser must not lose visible conversation history.
- Reopening a conversation resumes the same identity; "new chat" creates a new identity.
- The UI may use local browser state only as a convenience for the last-opened conversation; durable history itself must come from Odyssey state.
- Initial titles/grouping should be deterministic and inexpensive (for example first meaningful user message + date); do not add an LLM only to name chats.
- App/capability-specific conversations are not implemented in UI-0, but the conversation contract must not prevent later optional app-scope metadata.

## Storage and authority

Conversation records are durable **non-knowledge state**, not canonical personal notes.

Conceptually:

```text
/data/odyssey/state/conversations/
        -> durable visible conversation records

/data/odyssey/vault/
        -> canonical current personal knowledge
```

Requirements:

- use the existing durable `state/` authority boundary;
- keep conversation records logically isolated from ordinary note scans, embeddings, and personal-knowledge retrieval;
- prefer human-readable Markdown-like records, initially one durable record per conversation unless the architecture challenge proves a simpler safer layout;
- preserve visible user messages, final visible Odyssey responses, timestamps, `conversation_id`, `request_id`, stable actor/user correlation, and only bounded typed outcome metadata needed for resume/retrieval/audit;
- never persist hidden chain-of-thought, raw prompts, unrestricted provider payloads, credentials, or arbitrary intermediate model responses;
- a prior user/assistant turn records what was said, not what is currently true.

The filesystem representation must not use an untrusted external identity value directly as an unchecked path component. Conversation ownership should be based on the validated internal Odyssey actor/user identity boundary.

## Request and idempotency contract

The existing request path gains conversation correlation without creating a second semantic authority.

- browser requests carry a stable `conversation_id` for the active chat;
- every visible request/response turn remains correlated by the existing `request_id`;
- retrying the same `request_id` must not duplicate a persisted user or Odyssey turn;
- persistence failure must fail closed rather than silently presenting a conversation as durably saved when it is not;
- existing knowledge writes continue through Core and Git exactly as today; conversation persistence must not bypass or replace those paths.

The architecture challenge must choose the narrowest clean API/product projection for create/list/load/resume while preserving the existing same-origin protected product boundary.

## Conversational semantics

A resumed conversation should eventually behave like the same conversation, not merely display old text. UI-0 therefore includes the active-conversation continuity slice, but it must remain **context on demand**.

The same Luna-first planner remains the semantic interpreter:

```text
current request
      |
      v
planner pass 1
      |
      +--> self-contained PLAN / CLARIFY
      |        -> no conversation text loaded
      |
      `--> context needed
               |
               v
       bounded active-conversation retrieval
               |
               v
       same planner pass 2
               |
               v
       ordinary validated plan
```

Do not always send the last N turns and do not add a permanent second routing/rewrite model for this phase.

Authority remains explicit:

```text
current request          -> current intent
conversation evidence    -> what was said / referent evidence
canonical personal notes -> authority for current personal facts
```

If conversation evidence identifies a referent, the final current-fact answer should still be grounded in canonical knowledge. If two plausible referents remain, Odyssey clarifies rather than guessing.

A self-contained request should preserve the current fast path: one planner pass and zero conversation-history text added to the model input.

## Acceptance criteria

UI-0 is complete only when deterministic and isolated-DEV/browser evidence demonstrates all of the following:

1. A new conversation receives a stable `conversation_id` and durable actor ownership.
2. User-visible user/Odyssey turns survive page reload and a fresh browser session and render in chronological order.
3. The user can list/open at least two independent conversations; reopening one restores only that conversation's visible history.
4. Continuing an existing conversation reuses its `conversation_id`; starting a new chat creates a distinct one.
5. Reusing the same `request_id` does not duplicate a persisted turn.
6. Durable history lives under the non-canonical `state/` boundary and does not appear in ordinary personal-note retrieval/indexing.
7. Stable self/actor correlation survives reopen without inferring user identity from conversation text.
8. A self-contained request does not load conversation text or add a second planner call.
9. An immediate omitted-referent follow-up such as `¿Dónde vive?` after discussing one unambiguous person can request bounded active-conversation evidence and resolve safely through the same planner flow.
10. Two plausible conversational referents fail closed to clarification rather than selecting one arbitrarily.
11. Old conversation wording cannot override contradictory current canonical personal knowledge for a current-fact question.
12. Hidden reasoning/prompts/provider payloads are absent from durable conversation records and browser history projections.
13. DEV evidence uses isolated synthetic/non-personal conversation data and proves PROD data/runtime/workflows remain untouched.
14. The normal mobile protected surface supports new/list/open/resume with no requirement for the user to choose an application or technical mode.

Because the planner structured contract will change for context-on-demand, production-model validation must follow the AGENTS.md model-facing-change policy: deterministic fail-closed tests plus focused live Luna-first evidence and regression sentinels before readiness.

## Out of scope

- cross-conversation semantic/history search such as "what did we discuss last month?";
- hierarchical daily/weekly/monthly/yearly conversation summaries;
- retention/deletion/export policy;
- nested threads; later branching should first try "Continue in new chat";
- app/capability routing, `@App`, Tasks, Projects, or Reminders;
- Notes browsing/editing;
- multi-user sharing/permissions beyond enforcing the existing authenticated actor ownership boundary;
- a new chat database/service/vector service/application server;
- a dedicated conversation rewrite/router model;
- production deployment before merge and explicit human authorization.

## Open decisions for the architecture challenge

1. Exact durable Markdown record layout and safe actor/conversation filesystem layout under `state/`.
2. Narrow same-origin API/workflow shape for create/list/load and request-time persistence.
3. Exact generic structured planner result for requesting active-conversation context without weakening the existing `RequestPlan` contract.
4. Bounded active-conversation retrieval algorithm and absolute item/byte/token ceilings; recency/relevance should drive semantics, ceilings only bound resources.
5. Atomic/idempotent persistence point relative to runtime result, answerer result, browser response, and Retry behavior.
6. Whether UI-0 should be delivered as two internal implementation slices (durable substrate/UI first, adaptive context second) inside one active PR while keeping the phase incomplete until both acceptance sets pass.
7. Minimal deterministic title/grouping rule for the first conversation list.

The challenge should prefer existing Core/state/runtime/n8n/browser boundaries and explicitly reject extra infrastructure unless a concrete acceptance criterion cannot be met cleanly without it.
