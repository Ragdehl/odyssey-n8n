# Future Odyssey help and conversation context

Status: **preserved product direction; first mobile E2E validated the need for conversational context, and the intended design is now context-on-demand rather than a fixed recent-message window**

## Product goal

Odyssey should support natural conversation without requiring the user to know where information is stored. The same conversational surface should understand immediate follow-ups, retrieve older conversation history when relevant, answer from canonical personal knowledge, and route product-help or specialized-capability requests appropriately.

```text
user speaks naturally
      |
      v
Odyssey decides which source/context/capability is needed
      |
      v
retrieve only the necessary evidence
      |
      v
answer remains grounded in the authority appropriate to that source
```

The user should not need to know whether something lives in personal knowledge, recent conversation, old conversation history, product help, or an application.

## First mobile E2E finding

The first protected mobile E2E made the missing conversation contract concrete:

```text
User: ¿Dónde trabaja Nora Vidal?
Odyssey: Nora Vidal trabaja en Airbus.
User: ¿Dónde vive?
```

The current product sends each browser submission independently, so the planner sees `¿Dónde vive?` with no referent and safely abstains. This establishes a product requirement: **follow-ups must be able to recover conversation context without making chat text canonical personal truth.**

The same E2E also exposed a distinct presentation requirement: visible conversations must persist across page/app reopen. That WhatsApp-like history/resume behavior is a product projection over the durable conversation records described below, not a second history store and not canonical personal knowledge. See [Future Odyssey product interface](future-product-interface.md#ui-0--persistent-conversation-history-and-resume).

## Configuration-driven extensibility is a design requirement

Conversation/history support must preserve Odyssey's schema/configuration-driven philosophy rather than accumulating concrete prompt branches.

`config/note-schema.json` already carries type/property descriptions, examples, retrieval guidance, and retrieval examples. Planner capabilities are projected dynamically from that schema. New canonical note types/properties whose semantics are already supported by Core should therefore flow through the planner without production code naming each concrete type.

Apply the same principle to non-canonical sources and specialized capabilities. Conversation history should **not** become a normal canonical note type merely to make the planner aware that it exists. A compact source/capability registry should eventually describe planner-visible sources, for example:

```json
{
  "sources": [
    {
      "id": "personal_knowledge",
      "description": "Current canonical user knowledge.",
      "authority": "current_personal_truth"
    },
    {
      "id": "current_conversation",
      "description": "Visible turns from the active conversation; useful for omitted referents and follow-ups.",
      "authority": "conversation_reference_evidence"
    },
    {
      "id": "conversation_history",
      "description": "What the user and Odyssey said in prior conversations; not current factual authority.",
      "authority": "historical_conversation_evidence"
    },
    {
      "id": "odyssey_help",
      "description": "User-facing Odyssey product documentation and capability guidance.",
      "authority": "product_documentation"
    }
  ]
}
```

The exact filename/schema is deferred. The contract is not: once the generic projection exists, adding another already-supported source/capability should normally be configuration + validation/tests, not a new hard-coded planner branch. The same principle should guide future Odyssey applications/manifests.

## Decided implementation sequence

### C1 — adaptive current-conversation context

Goal: make immediate follow-ups natural without sending a fixed number of prior messages to the model on every request.

The **same Luna-first planner** remains the first semantic interpreter. Do not add a dedicated conversation-rewrite model or router merely for this feature.

The first planner pass receives the current request plus compact configuration-derived source/capability descriptions, but **not an arbitrary fixed tail of chat text**. Its generic result contract may request additional conversation evidence when the current request cannot be safely interpreted alone.

Conceptually:

```text
current request
      |
      v
same Luna planner — pass 1
      |
      +--> self-contained PLAN / CLARIFY
      |        -> execute normally; zero chat-history tokens
      |
      `--> CONTEXT_NEEDED
               |
               v
       bounded conversation retrieval
               |
               v
       same Luna planner — pass 2
               |
               v
       ordinary validated plan
```

`CONTEXT_NEEDED` is conceptual wording; the exact generic structured contract must be designed and validated when C1 is implemented.

Conversation retrieval should be **relevance- and recency-driven, not “last N messages” driven**. For `¿Dónde vive?`, current-conversation retrieval should inspect the active conversation backwards and recover only enough evidence to identify the likely referent. If two plausible anchors remain, Odyssey clarifies rather than guessing.

Explicit historical wording such as `ayer`, `la semana pasada`, `hace dos meses`, or `cuando hablamos de Marta` may cause the planner to request `conversation_history` directly with the relevant temporal/semantic constraints rather than treating it as an immediate follow-up.

Any implementation must still enforce absolute resource/safety budgets (maximum bytes/tokens/items returned to the planner), but these are **ceilings**, not semantic rules about how many messages constitute context.

The authority invariant is:

```text
current request          = current user intent
conversation evidence    = evidence of what was said / reference resolution
canonical personal notes = authority for current personal facts
```

A prior assistant message must never become current truth merely because it resolves a pronoun.

### C2 — durable conversation records

Goal: preserve what the user and Odyssey visibly said so older conversations can later be queried and the product UI can restore/reopen prior chats.

Preferred initial representation:

- human-readable Markdown conversation records outside the canonical personal-knowledge vault;
- durable non-knowledge/history state, conceptually `/data/odyssey/state/conversations/`;
- one record per conversation/session rather than one canonical note per turn;
- stable `conversation_id` so reopening/continuing a chat resumes the same conversation identity;
- correlate turns through `conversation_id` and existing `request_id` values;
- preserve user-visible user messages, final Odyssey responses, timestamps, and bounded typed outcome metadata useful for retrieval/audit;
- support chronological re-rendering for the UI without making browser `localStorage` the durable authority;
- never persist hidden chain-of-thought, private model reasoning, raw provider prompts, or arbitrary intermediate model responses.

Conversation history records what was said; it is not automatically evidence that the content is currently true.

### C3 — scoped semantic conversation-history retrieval

Goal: support questions such as:

```text
¿Qué te pregunté ayer?
¿De qué hablamos hace dos meses sobre Marta?
Antes hablamos de una empresa para Marta, ¿cuál era?
```

Expose conversation history through the configuration-driven source/scope registry, not as a normal `type=conversation` in the personal note schema.

`PERSONAL_KNOWLEDGE` remains the default authority for current facts. `CONVERSATION_HISTORY` is selected when the request asks about prior discussion, wording, prior requests, or historical conversational references.

Reuse existing embedding/retrieval machinery where practical, with logical/index isolation so historical chat cannot contaminate ordinary personal retrieval. Do not introduce a second vector service or general-purpose search stack merely for conversation history.

### C4 — hierarchical conversation summaries for coarse-to-fine retrieval

This is a later optimization, but preserve it explicitly.

Raw conversation records remain the underlying evidence. Derived summaries may form a temporal hierarchy:

```text
raw turns / conversation records
          |
          +--> conversation summary
          |
          +--> daily summary
          |
          +--> weekly summary
          |
          +--> monthly summary
          |
          `--> yearly summary
```

The purpose is **navigation and candidate narrowing**, not replacing raw history as authority. A broad request can search coarse summaries first, identify promising periods, then descend to finer summaries and finally the relevant conversation/raw turns.

Example:

```text
"¿Cuándo estuvimos hablando de cambiar de coche el año pasado?"
        |
        v
search yearly/monthly summaries
        |
        v
candidate month(s)
        |
        v
weekly/daily/conversation evidence
        |
        v
raw supporting turns when precision matters
```

Summaries should be derived/rebuildable and keep pointers to child periods/conversations/request IDs. Generate only levels that real usage justifies; do not pre-compute every level for sparse history. If model-generated summaries are adopted, benchmark their cost and information-loss risk first.

### C5 — optional long-term optimization

Only after real usage shows a need, evaluate retention/deletion controls, compaction, cross-device/session continuation, incremental summary refresh, and richer links between conversation history, canonical notes, Git evidence, and semantic request history.

## Why history is a source, not a canonical note type

A canonical type does not solve authority semantics. For example:

```text
Canonical knowledge:
Marta -> lives in Lyon

Old conversation:
"Maybe Marta will move to Bordeaux."
```

`¿Dónde vive Marta?` must use current canonical knowledge. `¿Qué dijimos sobre si Marta se mudaba a Burdeos?` must use historical conversation evidence. That is fundamentally a **source/authority distinction**, not an entity-type distinction.

A conversation record may still carry internal metadata such as `kind: conversation`; it simply does not participate as an ordinary canonical personal-knowledge type.

## Token/cost strategy

The preferred architecture is now **context on demand**:

```text
self-contained request
   -> one planner call
   -> no conversation text loaded

context-dependent request
   -> planner asks for context
   -> retrieve only relevant conversation evidence
   -> second call to the same planner with that evidence
```

This trades occasional second-pass latency/cost for avoiding repeated chat-context tokens on every ordinary request. Benchmark against the simpler always-send-small-tail alternative before implementation; keep whichever has the better measured total cost/quality on real Odyssey usage.

Older history is never dumped into the model wholesale. Historical retrieval and later hierarchical summaries exist precisely to narrow evidence before it reaches a model.

## Relationship with semantic request history

Conversation history and semantic request history remain different views correlated through `request_id` and `conversation_id`:

```text
conversation history
  -> what the user and Odyssey visibly said

semantic request history
  -> validated request/plan/outcome evidence about what Odyssey did
```

Neither becomes canonical personal truth.

## Validation scenarios

Future implementation must cover immediate omitted referents, two plausible recent referents, explicit old-time references, current-fact questions contradicting old chat, historical questions that must not contaminate personal retrieval, configuration-added sources without concrete planner branches, coarse-to-fine summary retrieval, durable reopen/resume of visible conversations, and bounded resource behavior.

## Remaining deferred decisions

The implementation phase must still decide the exact source/capability registry schema, the structured planner result for requesting context, current-conversation storage before C2 persistence exists, absolute retrieval budgets, Markdown conversation layout, history index isolation, summary-generation policy, retention/deletion controls, and whether measured evidence ever justifies a separate routing model.

Do not introduce a new database, chat-history service, separate vector store, second general-purpose agent, or additional permanent model layer until real usage demonstrates that the simpler design is insufficient.
