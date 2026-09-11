# Future Odyssey help and conversation context

Status: **preserved product direction; first mobile E2E has now validated the need for bounded conversational context**

## Product goal

Odyssey should eventually support natural questions not only about the user's personal knowledge, but also about **Odyssey itself**:

```text
"¿Qué puede hacer Odyssey?"
"¿Cómo creo una nota?"
"¿Cómo funcionan las aplicaciones?"
"¿Y eso cómo lo hago desde el móvil?"
```

The user should be able to ask these questions through the same conversational surface rather than needing a separate manual or a completely separate assistant product.

This does not require a new application architecture by default. The smallest useful direction is a **help/product-knowledge scope** routed through the same general retrieval + bounded answerer pattern.

Real Odyssey Online use also established a later **general conversational** scope for ordinary requests such as “Hola, ¿qué tal?”. It should be evaluated as another capability of the same conversational surface, not assumed to require a separate app. Ordinary conversation is not durable Odyssey memory, must not fabricate personal knowledge, and may use the bounded session context described below. Personal knowledge answers remain grounded in authorized retrieved evidence.

## First mobile E2E finding

The first protected mobile E2E made the missing conversation contract concrete:

```text
User: ¿Dónde trabaja Nora Vidal?
Odyssey: Nora Vidal trabaja en Airbus.
User: ¿Dónde vive?
```

The last request is naturally understandable to a person, but the current product sends each browser submission independently. The planner therefore receives `¿Dónde vive?` without the recent turns and safely returns no result rather than inventing a referent.

This establishes a product requirement: **ordinary follow-ups must be able to reuse bounded recent conversation context without turning conversation text into canonical personal knowledge.**

## Decided implementation sequence

Implement conversation continuity in three functional stages. A fourth optimization stage is optional and should be justified by real usage rather than built pre-emptively.

### C1 — bounded recent-session context

Goal: make immediate follow-ups such as `¿Dónde vive?`, `¿y cuándo fue?`, or `¿y el otro?` natural without creating a new model layer or persistent-history system.

Initial contract:

- keep the current Luna-first planner as the first semantic interpreter;
- do **not** add a dedicated conversation-rewrite LLM, router LLM, or agent;
- send the current request together with bounded recent visible turns;
- start with at most **three complete user/Odyssey exchanges (six messages)** before the current request;
- also enforce an initial **6,000-character total context cap**, trimming the oldest complete turns first;
- do not summarize recent context in C1; replay the small bounded window directly;
- treat recent assistant text as reference-resolution context, not as canonical factual authority;
- if the referent remains ambiguous, clarify rather than guess.

The browser/product request may evolve conceptually from:

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

The exact field names remain an implementation detail, but the product boundary must validate roles, message count, and size rather than accepting unbounded arbitrary history.

The planner should receive the recent context as an explicit secondary input and use it only to interpret ellipsis, pronouns, follow-ups, and omitted referents in the **current** request. For the example above, the same Luna planner should be able to produce the ordinary personal-knowledge retrieval plan for `Nora Vidal`; normal retrieval then grounds the answer from canonical knowledge.

A model-facing prompt change will therefore be required, but it should be a narrow inheritance-first extension of the validated Luna-first planner prompt. The essential instruction is:

```text
current request = authoritative intent
recent context = reference-resolution evidence
canonical retrieval = factual authority
```

Prior assistant wording must never become current personal truth merely because it appears in recent context. Material prompt changes require the normal deterministic and focused live-evidence gates from `AGENTS.md`.

C1 should remain cheap: one existing planner call, the existing retrieval path, and the existing answerer where needed. No additional LLM call is justified merely to resolve recent conversational references.

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

Do not model conversation history as an ordinary personal note type. Expose it to planning as a **logical retrieval scope/capability** instead.

Conceptually the planner may know compact scope descriptions such as:

```text
PERSONAL_KNOWLEDGE
  Current canonical user knowledge. Use for questions about what is true/known now.

CONVERSATION_HISTORY
  What the user and Odyssey said in prior conversations. Use for questions about prior discussion,
  wording, requests, or historical conversational references. Never treat it as current truth.

ODYSSEY_HELP
  User-facing product documentation and capability guidance.
```

This follows the same principle already used for capability/app descriptions: the planner knows what sources/capabilities exist and chooses the appropriate one from the user's natural request. It does **not** require a second semantic interpreter.

When C3 is implemented, prefer an explicit retrieval-source/scope contract at the planner/application boundary over a canonical `conversation` note type. `PERSONAL_KNOWLEDGE` should remain the default. `CONVERSATION_HISTORY` should be selected when the request semantically asks about past conversation/history, or when a bounded recent-context reference clearly points to historical conversation evidence. A generic unresolved pronoun with no useful anchor should clarify rather than search the user's entire history speculatively.

Reuse the existing embedding/retrieval machinery where practical, with logical/index isolation so conversation hits cannot contaminate ordinary personal-knowledge results. Do not introduce a second vector service or general-purpose search stack merely for conversation history.

### C4 — optional compression and retention optimization

Only after real usage shows a need, evaluate:

- summaries for very long active conversations;
- chunking/compaction strategies for old conversation records;
- retention controls;
- cross-device/session continuation;
- richer links between conversation history, affected canonical notes, and Git/request evidence.

C4 is an optimization stage, not a prerequisite for natural immediate follow-ups or basic historical search.

## Why conversation history is a scope, not a canonical note type

Adding `conversation` to the ordinary note schema would not actually eliminate model-facing work: the planner would still need instructions/examples that explain **when** to choose that type and how it differs from personal truth. It would also make internal history participate in normal canonical semantics unless many exceptions were added.

For example:

```text
Canonical knowledge:
Marta -> lives in Lyon

Old conversation:
"Maybe Marta will move to Bordeaux."
```

A normal query such as `¿Dónde vive Marta?` must retrieve the canonical Marta knowledge, not an old speculative chat message that happens to be semantically similar. Conversely, `¿qué dijimos sobre si Marta se mudaba a Burdeos?` should search conversation history.

That distinction is naturally a **source/scope distinction**, not an entity-type distinction.

A conversation record may still have internal metadata such as `kind: conversation`, but that metadata belongs to the history representation and is not part of the canonical personal note ontology.

## Help as a knowledge scope, not a second personal vault

User-facing Odyssey documentation can be represented as ordinary human-readable Markdown knowledge, but it should remain logically separated from the user's personal knowledge so product documentation cannot contaminate ordinary personal retrieval.

Conceptually:

```text
user request
     |
     v
scope / intent interpretation
     |
     +--> PERSONAL_KNOWLEDGE
     |
     +--> CONVERSATION_HISTORY
     |
     +--> ODYSSEY_HELP
     |
     `--> OTHER CAPABILITY / AMBIGUOUS
```

For `ODYSSEY_HELP`, retrieval searches only the product-help corpus. The resulting grounded evidence can then be sent through the same bounded answerer contract used for normal Odyssey retrieval answers.

The exact physical storage is intentionally deferred. A separate vault is one valid option, but it is **not yet a requirement**. Product help may be better represented as versioned, read-only Markdown shipped with or generated from the Odyssey product documentation. The important contract is logical scope isolation, not a particular filesystem layout.

Help content should be written for users, not copied blindly from developer architecture documentation. It may include:

- what Odyssey can and cannot do;
- how common user actions work;
- explanations of applications/capabilities;
- privacy and sharing behavior;
- examples of useful requests;
- troubleshooting and product limitations;
- version-specific behavior when relevant.

## Routing strategy

Do not introduce an expensive general model call solely to recognize help or history intent.

Start from the simplest measured strategy:

1. let the existing Luna-first planner interpret the current request using compact descriptions of available scopes/capabilities;
2. use deterministic or explicit UI signals when they genuinely simplify the case;
3. use ordinary scoped retrieval after the planner has selected the source;
4. fail safely or ask for clarification when a request genuinely mixes scopes or has an unresolved referent.

A separate routing model should be introduced only if measured evidence later shows that the existing planner contract cannot make these choices reliably or economically.

Representative mixed cases must be considered later, for example:

```text
"¿Puede Odyssey recordarme lo que compré en Carrefour?"
```

That question may ask simultaneously about product capability and the user's own stored knowledge. The planner must not silently leak personal knowledge into a product-help answer or vice versa.

## Conversation context is not durable memory

A useful conversational interface needs follow-up understanding:

```text
User: ¿Cómo funcionan las tareas?
Assistant: ...
User: ¿Y cómo creo una?
```

The second request needs enough recent context to understand what `una` refers to.

```text
recent conversation turns
        |
        v
bounded session context
        + current request
        |
        v
same Luna-first planner
        |
        v
normal scoped retrieval / write / capability path
```

The user saying something in conversation does **not** automatically make it durable personal knowledge.

```text
conversation context  !=  Odyssey memory

"¿y luego qué?"       -> recent session context
"recuerda que..."     -> normal Odyssey write path
```

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

## Likely product shape

A mature request may conceptually flow as follows:

```text
current request
   +
recent bounded context
   |
   v
same Luna-first planner
   |
   +--> PERSONAL_KNOWLEDGE
   |       |
   |       v
   |   personal retrieval / mutation
   |
   +--> CONVERSATION_HISTORY
   |       |
   |       v
   |   scoped history retrieval
   |
   +--> ODYSSEY_HELP
   |       |
   |       v
   |   product-help retrieval
   |
   `--> other capability / ambiguity
           |
           v
       existing delegation / clarification path

retrieved grounded evidence
          |
          v
same bounded answerer
          |
          v
conversational response
```

The planner chooses **how to interpret the request and where to retrieve**; it does not become a second knowledge authority. The answerer remains grounded in evidence from the selected scope.

## Validation scenarios for the future

Before adopting each stage, test at least:

- `¿Dónde vive?` after immediately discussing one person;
- follow-up pronouns/references across two or three recent exchanges;
- two plausible recent referents -> clarification, not guessing;
- old assistant text contradicting canonical knowledge -> canonical knowledge wins for current-fact questions;
- explicit `remember this` requests still use the normal Odyssey write path;
- direct historical questions such as `¿qué te pregunté ayer?` select conversation history;
- ordinary personal questions do not search conversation history;
- direct product-help questions do not search personal knowledge;
- mixed help + personal-knowledge requests fail safely or preserve both intents explicitly;
- no leakage from personal knowledge into help-only answers;
- no accidental persistence of ordinary chat turns as durable personal memory;
- long-session behavior remains bounded rather than sending unlimited history to models.

## Remaining deferred decisions

Decide from implementation evidence and real Odyssey Online usage:

1. whether C1 recent context should live only in browser/request state or gain short-lived server/session state after the minimal version;
2. the exact Markdown layout and metadata schema for C2 conversation records;
3. the exact planner/application representation of source scope in C3;
4. whether help content lives in a dedicated vault, a versioned read-only Markdown corpus, or another minimal representation;
5. whether long conversations ever need summarization rather than simple bounded replay plus historical retrieval;
6. retention and deletion controls for durable conversation history;
7. whether a later measured need justifies a separate router model despite the default decision to reuse the Luna-first planner.

Do not introduce a new database, chat-history service, separate vector store, second general-purpose agent, or additional LLM hop until real usage demonstrates that the simpler staged design is insufficient.

## Related product observability direction

The help/conversation surface should remain separate from product telemetry concerns. Odyssey's future simple-vs-advanced usage, token, cost, diagnostic, graph, and month-end projection direction is preserved in [Future Odyssey product usage observability](future-product-usage-observability.md).
