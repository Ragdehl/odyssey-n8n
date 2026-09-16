# Future Odyssey help and conversation context

Status: **UI-0 one-pass recent continuity is current; historical conversation retrieval and derived
memory remain deferred.**

## Purpose

Odyssey is a personal memory based on local notes, consultable and modifiable through natural
language. Conversation helps the user interact naturally with that memory; it is not a second
personal-knowledge authority or a general assistant-memory product.

## Current UI-0 boundary

UI-0 keeps one durable actor-scoped main transcript outside canonical Markdown. A deterministic
bounded window of complete recent visible turns is supplied to the existing Luna-first planner in
the same request. It may resolve linguistic continuity such as a person referred to by “ella” or
“entonces”; it never becomes a current-fact source, retrieval filter, or automatic mutation fact.

```text
recent transcript -> planner interpretation -> validated plan -> canonical Markdown retrieval/write
```

Canonical Markdown remains authority for current personal facts. If the recent window still leaves
the referent or write meaning ambiguous, Odyssey clarifies. UI-0 has no `CONTEXT_NEEDED` outcome,
second planner pass, context router, summary model, conversation semantic index, or cross-chat
search. The detailed current contract is [UI-0 durable main conversation](ui-0-durable-conversations.md).

## Deferred historical direction

The following capabilities remain possible only after direct use establishes their need and an
architecture challenge selects bounded authority and retention contracts:

- historical questions such as “what did I say on 1 February 2024?”;
- search over older transcript data, cross-conversation discovery, or conversation embeddings;
- generated conversation/day/week/month/year summaries or summary hierarchies;
- topic splitting, multiple-chat management, threads, or general-purpose assistant memory;
- retention, deletion, export, and user-visible history navigation policy.

Raw transcript timestamps and stable request correlation are retained so a later historical feature
can identify supporting turns. Any future index or summary is derived navigation evidence only; it
must point to raw durable records and never replace canonical note authority.

## Authority and safety invariants

1. Conversation records are durable non-knowledge state under Odyssey `state/`, not vault notes,
   index entries, embeddings, or retrieval corpus.
2. A prior user or Odyssey message records what was said, not what is currently true.
3. Only a validated planner result can cross from conversational wording into canonical
   retrieval/mutation; no raw transcript is supplied as retrieval query expansion.
4. Prior assistant text never supplies a current fact or mutation target. Prior explicit user text
   may be used only when the ordinary validated write contract represents it safely.
5. Actor ownership is based on validated internal identity, never an unchecked external subject.
6. Durable records exclude prompts, hidden reasoning, raw provider payloads, credentials, and
   unrelated personal content.

## Historical checkpoint

The earlier UI-0 exploration tried an explicit `CONTEXT_NEEDED` structured outcome and a bounded
second planner pass. Focused live gates showed the additional full planner pass was both costly and
unnecessary for ordinary immediate continuity. The product direction now favors one bounded recent
window in the existing planner call. This preserves the experiment as evidence without making it
the current architecture.
