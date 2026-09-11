# Future Odyssey help and conversation context

Status: **preserved product direction; first mobile E2E has now validated the need for bounded conversational context**

## Product goal

Odyssey should support natural conversation without requiring the user to know where information is stored. The same conversational surface should eventually understand immediate follow-ups, retrieve older conversation history when explicitly relevant, answer from canonical personal knowledge, and route product-help or specialized-capability requests appropriately.

The core product principle is:

```text
user speaks naturally
      |
      v
Odyssey decides which bounded context / source / capability is relevant
      |
      v
answer remains grounded in the authority appropriate to that source
```

## First mobile E2E finding

The first protected mobile E2E made the missing conversation contract concrete:

```text
User: ¿Dónde trabaja Nora Vidal?
Odyssey: Nora Vidal trabaja en Airbus.
User: ¿Dónde vive?
```

The last request is naturally understandable to a person, but the current product sends each browser submission independently. The planner therefore receives `¿Dónde vive?` without the recent turns and safely returns no result rather than inventing a referent.

This establishes a product requirement: **ordinary follow-ups must be able to reuse bounded recent conversation context without turning conversation text into canonical personal knowledge.**

## Configuration-driven extensibility is a design requirement

Conversation/history support must preserve Odyssey's existing schema-driven philosophy rather than accumulating hard-coded prompt branches.

`config/note-schema.json` already carries machine-readable type/property descriptions, examples, retrieval guidance, and retrieval examples. Production planner capabilities are projected dynamically from that schema. New canonical note types/properties whose semantics are already supported by Core should therefore flow through the planner without production code naming each concrete type.

Apply the same pattern to non-canonical sources and specialized capabilities. Conversation history should **not** become a canonical note type merely to make the planner aware that it exists. Instead, introduce a compact configuration/registry contract for planner-visible sources/scopes when C3 is implemented. Conceptually:

```json
{
  "sources": [
    {
      "id": "personal_knowledge",
      "description": "Current canonical user knowledge.",
      "authority": "current_personal_truth",
      "examples": ["¿Dónde vive Marta?"]
    },
    {
      "id": "conversation_history",
      "description": "What the user and Odyssey said in prior conversations; not current factual authority.",
      "authority": "historical_conversation_evidence",
      "examples": ["¿Qué te pregunté hace dos meses sobre Marta?"]
    },
    {
      "id": "odyssey_help",
      "description": "User-facing Odyssey product documentation and capability guidance.",
      "authority": "product_documentation",
      "examples": ["¿Cómo funcionan las tareas en Odyssey?"]
    }
  ]
}
```

The exact filename and schema are deferred, but the contract is not: once the generic source/capability projection exists, adding another supported source should normally be a configuration change plus validation/tests, not a new hard-coded planner branch. The generic planner prompt should receive a projected source-capability block, analogous to the existing schema-derived retrieval/write capability blocks.

The same principle should guide future Odyssey applications/capabilities: declarative descriptors should tell the planner what capabilities exist and when they are relevant; generic execution boundaries own how a selected capability is invoked. Do not require editing the base planner prompt for every new application unless the generic contract itself needs to evolve.

## Decided implementation sequence

Implement conversation continuity in three functional stages. A fourth optimization stage is optional and should be justified by real usage rather than built pre-emptively.

### C1 — bounded recent-session context

Goal: make immediate follow-ups such as `¿Dónde vive?`, `¿y cuándo fue?`, or `¿y el otro?` natural without creating a new model layer or persistent-history system.

Initial contract:

- keep the current Luna-first planner as the first semantic interpreter;
- do **not** add a dedicated conversation-rewrite LLM, router LLM, or agent;
- provide the current request together with a small bounded tail of recent visible conversation;
- start with the **last two complete user/Odyssey exchanges** as the normal context window;
- permit at most **three complete exchanges (six messages)** as a hard message-count ceiling;
- enforce an initial **6,000-character absolute safety cap**, trimming the oldest complete exchange first; this is a ceiling, not a target payload size;
- do not summarize recent context in the first implementation;
- treat recent assistant text only as reference-resolution/conversation evidence, never as canonical factual authority;
- if the referent remains ambiguous, clarify rather than guess.

Conceptually the browser/product request may evolve from:

```json
{
  "request": "¿Dónde vive?",
  "request_id": "web-..."
}
```

to a bounded shape such as:

```json
{
  "request": "¿Dónde vive?",
  "request_id": "web-...",
  "conversation_id": "conversation-...",
  "recent_context": [
    {"role": "user", "text": "¿Dónde trabaja Nora Vidal?"},
    {"role": "assistant", "text": "Nora Vidal trabaja en Airbus."}
  ]
}
```

The exact field names remain an implementation detail. The product boundary must validate roles, message count, and size rather than accepting unbounded arbitrary history.

The same Luna planner receives this recent context as a secondary input. It uses it only to interpret ellipsis, pronouns, omitted referents, and conversational follow-ups in the **current** request. For the example above, the planner should produce the ordinary personal-knowledge retrieval plan for Nora Vidal; normal canonical retrieval then supplies the factual evidence for the answer.

Do not create a second LLM call just to decide whether context is needed. The simplest C1 implementation can include the small recent tail on each active-conversation planner request. This adds bounded input tokens but no extra model hop. A deterministic pre-filter may be evaluated later only if measured cost justifies the complexity and does not harm natural follow-ups.

The planner-facing invariant is:

```text
current request      = authoritative user intent
recent conversation  = reference-resolution evidence
selected source      = determines what kind of evidence is being requested
canonical retrieval  = factual authority for current personal-knowledge answers
```

Recent context should be appended as data to the planner input, not implemented as per-feature prose branches in the base prompt. The generic planner contract needs one stable rule explaining the authority of recent context; concrete note types, sources, and applications remain configuration-driven wherever the generic contracts support them.

Material model-facing contract changes still require the deterministic and focused live-evidence gates from `AGENTS.md`.

### C2 — durable conversation records

Goal: preserve what the user and Odyssey actually said so Odyssey can later answer questions about older conversations.

Preferred first representation:

- use **human-readable Markdown conversation records**, but keep them outside the canonical personal-knowledge vault;
- store them as durable non-knowledge/history state, conceptually under `/data/odyssey/state/conversations/`;
- prefer **one conversation record per conversation/session**, not one canonical note per turn;
- correlate turns through `conversation_id` and existing `request_id` values;
- preserve user-visible user messages and final Odyssey responses, timestamps, and bounded typed outcome metadata useful for audit/retrieval;
- never persist hidden chain-of-thought, private model reasoning, raw provider prompts, or arbitrary intermediate model responses.

This is intentionally different from creating a normal `type=conversation` or `type=user_request` in `config/note-schema.json`.

Conversation history is evidence about **what was said**, not automatically evidence that the content is currently true. Keeping it outside the canonical schema prevents normal identity resolution, bulk selection, writes, and personal-knowledge retrieval from silently treating old chat text as authoritative knowledge.

### C3 — scoped semantic conversation-history retrieval

Goal: support natural historical questions such as:

```text
"¿De qué hablamos la semana pasada?"
"¿Qué te pregunté hace dos meses sobre Marta?"
"Antes hablamos de una empresa para Marta, ¿cuál era?"
```

Do not model conversation history as an ordinary personal note type. Expose it to planning through the configuration-driven **source/scope registry** described above.

`PERSONAL_KNOWLEDGE` remains the default authority for current personal facts. `CONVERSATION_HISTORY` is selected when the request asks about prior discussion, wording, prior requests, or historical conversational references. A generic unresolved pronoun with no useful recent anchor should clarify rather than search the user's entire history speculatively.

Reuse existing embedding/retrieval machinery where practical, with logical/index isolation so conversation hits cannot contaminate ordinary personal-knowledge results. Do not introduce a second vector service or general-purpose search stack merely for conversation history.

### C4 — optional compression and retention optimization

Only after real usage shows a need, evaluate compact session-state representations, summaries for long active conversations, chunking/compaction of old records, retention controls, cross-device/session continuation, and richer links between conversation history, affected canonical notes, and Git/request evidence.

One possible measured optimization is to replace part of repeated raw recent text with compact structured anchors derived from already-available typed results (for example recent canonical entity names/selections) while keeping enough visible text to resolve conversational references. This must remain deterministic and must not introduce another LLM call merely to save planner input tokens.

## Why conversation history is a scope, not a canonical note type

Adding `conversation` to the ordinary note schema would not eliminate model-facing semantics. The planner would still need to know when prior conversation is relevant and, crucially, that old chat text is not current factual authority. It would also make internal history participate in normal canonical semantics unless many exceptions were added.

For example:

```text
Canonical knowledge:
Marta -> lives in Lyon

Old conversation:
"Maybe Marta will move to Bordeaux."
```

A normal query such as `¿Dónde vive Marta?` must retrieve the canonical Marta knowledge, not an old speculative chat message that happens to be semantically similar. Conversely, `¿qué dijimos sobre si Marta se mudaba a Burdeos?` should search conversation history.

That distinction is a **source/authority distinction**, not an entity-type distinction.

A conversation record may still have internal metadata such as `kind: conversation`, but that metadata belongs to the history representation and is not part of the canonical personal note ontology.

## Token/cost strategy

Do **not** send the entire conversation history to Luna on every request.

C1 sends only the small recent tail needed for immediate conversational continuity. C3 retrieves older conversation evidence only when the planner selects the conversation-history source. Therefore the mature flow is conceptually:

```text
current request
+ small recent tail
+ compact configured capability/source descriptions
          |
          v
   same Luna-first planner
          |
          +--> ordinary personal request -> no old chat history loaded
          |
          `--> historical-conversation request
                    |
                    v
             retrieve only relevant old history
```

The 6,000-character C1 limit is an abuse/safety ceiling, not the expected per-request context. Normal short exchanges should be far below it. Measure real token/cost telemetry before adding heuristics or compression complexity.

## Help as another scoped source

User-facing Odyssey documentation can be represented as human-readable Markdown, but it must remain logically separated from personal knowledge so product documentation cannot contaminate ordinary personal retrieval. The same source/capability registry direction can describe `ODYSSEY_HELP` without a new planner layer.

Help content should be written for users and may cover what Odyssey can/cannot do, common actions, applications/capabilities, privacy/sharing, examples, troubleshooting, limitations, and version-specific behavior.

## Relationship with semantic request history

Odyssey already preserves `request_id` and the semantic-request-history direction described in [Future semantic request history](phase-17-request-records.md). Durable conversation records should reuse that identity rather than inventing a disconnected audit/history identity.

The two views remain conceptually different:

```text
conversation history
  -> what the user and Odyssey visibly said

semantic request history
  -> validated request/plan/outcome evidence about what Odyssey did
```

They can be correlated through `request_id` and `conversation_id`, but neither becomes canonical personal truth.

## Mature product shape

```text
current request
   +
small bounded recent context
   +
configuration-derived source/capability descriptions
   |
   v
same Luna-first planner
   |
   +--> PERSONAL_KNOWLEDGE -> personal retrieval / mutation
   |
   +--> CONVERSATION_HISTORY -> scoped history retrieval
   |
   +--> ODYSSEY_HELP -> product-help retrieval
   |
   `--> other capability / ambiguity -> existing delegation / clarification path

retrieved grounded evidence
          |
          v
same bounded answerer
          |
          v
conversational response
```

The planner interprets the request and selects the appropriate generic action/source/capability contract; it does not become a second knowledge authority.

## Validation scenarios

Before adopting each stage, test at least:

- `¿Dónde vive?` after immediately discussing one person;
- follow-up references across two or three recent exchanges;
- two plausible recent referents -> clarification, not guessing;
- old assistant text contradicting canonical knowledge -> canonical knowledge wins for current-fact questions;
- explicit `remember this` requests still use the normal Odyssey write path;
- direct historical questions such as `¿qué te pregunté ayer?` select conversation history;
- ordinary personal questions do not search conversation history;
- adding a supported planner-visible source through configuration does not require a concrete production branch naming that source;
- direct product-help questions do not search personal knowledge;
- mixed scopes fail safely or preserve both intents explicitly;
- no accidental persistence of ordinary chat turns as durable personal memory;
- long-session behavior remains bounded rather than sending unlimited history to models.

## Remaining deferred decisions

Decide from implementation evidence and real Odyssey Online usage:

1. exact configuration filename/schema for planner-visible sources/capabilities;
2. whether C1 recent context initially lives only in browser/request state or short-lived server/session state;
3. exact Markdown layout and metadata schema for C2 conversation records;
4. exact generic planner/application representation of source selection in C3;
5. whether long conversations need structured-anchor compression or summarization;
6. retention/deletion controls for durable conversation history;
7. whether a later measured need justifies a separate router model despite the default decision to reuse the Luna-first planner.

Do not introduce a new database, chat-history service, separate vector store, second general-purpose agent, or additional LLM hop until real usage demonstrates that the simpler staged design is insufficient.

## Related product observability direction

The help/conversation surface should remain separate from product telemetry concerns. Odyssey's future simple-vs-advanced usage, token, cost, diagnostic, graph, and month-end projection direction is preserved in [Future Odyssey product usage observability](future-product-usage-observability.md).
