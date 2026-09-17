# Future Odyssey help and conversation context

Status: **UI-0 one-pass recent continuity is current. Conversation persistence is UX and
operational state, not a historical knowledge source.**

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

## Historical knowledge is canonical knowledge work

Questions such as “¿Qué apunté sobre Marta hace dos años?” or “¿Qué sabía de Marta entonces?” are
future canonical knowledge chronology/retrieval work. They should use canonical notes, atomic-fact
capture provenance, note-level dates, and canonical Git/request history as appropriate—not older
chat text. The existing knowledge model distinguishes `captured_at` from `happened_at`; this is not
a reason to add redundant universal per-fact timestamps or change the note schema.

Exact transcript questions such as “¿Qué palabras escribí en el chat el 1 de febrero de 2024?” are
not a core Odyssey memory capability. Historical transcript search, cross-conversation discovery,
embeddings, or generated transcript summaries are not expected follow-on work from UI-0. They would
need separate explicit product justification, retention policy, and authority review before entering
any roadmap.

Raw transcript timestamps and stable request correlation serve visible continuity and safe
operational history. They do not reserve a transcript-memory feature or make the transcript a
retrieval corpus.

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
