# Future Odyssey help and conversation context

Status: **preserved product direction; implementation deferred until after the first Odyssey Online MVP usage**

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

Real Odyssey Online use also established a later **general conversational** scope for ordinary requests
such as “Hola, ¿qué tal?”. It should be evaluated as another capability of the same conversational
surface, not assumed to require a separate app. Ordinary conversation is not durable Odyssey memory,
must not fabricate personal knowledge, and may later use the same bounded session context described
below. Personal knowledge answers remain grounded in authorized retrieved evidence.

## Help as a knowledge scope, not a second personal vault

User-facing Odyssey documentation can be represented as ordinary human-readable Markdown knowledge, but it should remain logically separated from the user's personal knowledge so product documentation cannot contaminate ordinary personal retrieval.

Conceptually:

```text
user request
     |
     v
scope / intent routing
     |
     +--> PERSONAL_KNOWLEDGE
     |
     +--> ODYSSEY_HELP
     |
     `--> MIXED / AMBIGUOUS
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

Do not introduce an expensive general model call solely to recognize help intent.

Start from the simplest measured routing strategy:

1. deterministic or explicit UI signals where available;
2. cheap semantic routing over compact scope descriptions/examples;
3. a low-cost model such as Luna only when ambiguity remains and evidence shows it improves routing;
4. fail safely or ask for clarification when a request genuinely mixes product-help and personal-knowledge intent.

This can reuse the general capability-routing principles already preserved for Odyssey applications, but `ODYSSEY_HELP` need not become a full installable app merely to answer product questions.

Representative mixed cases must be considered later, for example:

```text
"¿Puede Odyssey recordarme lo que compré en Carrefour?"
```

That question may ask simultaneously about product capability and the user's own stored knowledge. The router should not silently leak personal knowledge into a product-help answer or vice versa.

## Conversation context is not durable memory

A useful conversational interface needs follow-up understanding:

```text
User: ¿Cómo funcionan las tareas?
Assistant: ...
User: ¿Y cómo creo una?
```

The second request needs enough recent context to understand what `una` refers to.

That requirement should be implemented first as a **bounded session context**, separate from canonical Odyssey memory and separate from semantic request history.

```text
recent conversation turns
        |
        v
bounded session context
        + current request
        |
        v
planner / router / answerer as needed
```

Session context should initially be:

- limited to the current conversation/session;
- bounded in number/size of turns or by a compact summary when justified;
- available only to components that need it for the current request;
- excluded from canonical Markdown knowledge unless the user explicitly asks Odyssey to remember something;
- free of hidden chain-of-thought or private model reasoning.

The user saying something in conversation does **not** automatically make it durable knowledge.

```text
conversation context  !=  Odyssey memory

"¿y luego qué?"       -> session context
"recuerda que..."     -> normal Odyssey write path
```

## Relationship with semantic request history

Odyssey already preserves `request_id` and a deferred direction for semantic request history. That future capability is different from live conversational context.

Session context answers:

```text
"¿Qué significa 'eso' en este turno?"
```

Persisted semantic request history may later answer:

```text
"¿De qué hablamos la semana pasada?"
"¿Qué te pedí ayer?"
```

Do not force the first conversation-context implementation to solve long-term history. Likewise, do not turn every chat turn into a canonical `user_request` note merely to support follow-ups.

A future bridge may reuse `request_id` to correlate stored semantic history with turns, results, or Git evidence, but retention, indexing, privacy, and history retrieval remain separate contracts.

See [Future semantic request history](phase-17-request-records.md).

## Likely product shape

A later Odyssey Online request may conceptually flow as follows:

```text
current request
   +
recent session context
   |
   v
cheap scope/router decision
   |
   +--> PERSONAL
   |       |
   |       v
   |   personal retrieval
   |
   +--> HELP
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

The router chooses **where to retrieve**; it does not become a second knowledge authority. The answerer remains grounded in the evidence supplied from the selected scope.

## Validation scenarios for the future

Before adopting this capability, test at least:

- direct product-help questions;
- ordinary personal questions that must not search product help;
- ambiguous wording that could refer to the current conversation;
- follow-up pronouns/references across recent turns;
- mixed help + personal-knowledge requests;
- outdated product-help content after a product behavior changes;
- no leakage from personal knowledge into help-only answers;
- no accidental persistence of ordinary chat turns as durable memory;
- explicit `remember this` requests still use the normal Odyssey write path;
- long-session behavior remains bounded rather than sending unlimited history to models.

## Deferred decisions

Decide from real Odyssey Online usage:

1. whether help content lives in a dedicated vault, a versioned read-only Markdown corpus, or another minimal representation;
2. whether help scope is selected through deterministic routing, embeddings, Luna, or a measured combination;
3. the exact bounded session-context representation and retention window;
4. whether session context lives in browser state, server/session state, or another minimal temporary layer;
5. when a long conversation should be summarized rather than replayed turn-by-turn;
6. how mixed personal/help requests are represented at the planner/application boundary;
7. how persistent semantic request history later reconnects with session conversations without contaminating canonical knowledge retrieval.

Do not introduce a new database, chat-history service, separate vector store, or second general-purpose agent until real usage demonstrates that the simpler scoped-retrieval + bounded-session-context design is insufficient.

## Related product observability direction

The help/conversation surface should remain separate from product telemetry concerns. Odyssey's future simple-vs-advanced usage, token, cost, diagnostic, graph, and month-end projection direction is preserved in [Future Odyssey product usage observability](future-product-usage-observability.md).
