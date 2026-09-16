# Product Vision

Odyssey turns fragments accumulated through life and work into durable, connected knowledge that the user, applications, and AI agents can safely return to and use.

Its enduring promise is:

> **Capture without friction, organize automatically, and retrieve the right information when it becomes useful.**

Its product mantra is:

> **Odyssey is a personal memory based on local notes, consultable and modifiable through natural language.**

This mantra is a scope guard, not marketing decoration. When a proposed feature primarily makes Odyssey a more general chat, messaging, or assistant product without materially improving how users capture, retrieve, understand, or maintain their note-based memory, it needs strong evidence before it belongs in Core or the main product roadmap. Conversational UX should make the note memory easier to use; it must not become a competing product goal or a second knowledge authority.

## Product principles

### Capture first

A user should be able to write naturally without choosing a folder, form, note type, property set, or ontology first. One message may mention several subjects or combine a question with new knowledge.

Odyssey interprets that input behind explicit contracts and preserves the resulting knowledge in human-readable form.

### Preserve identity

Knowledge about the same person, project, concept, product, document, or other entity should accumulate around one stable logical identity when the evidence supports it.

```text
new statement
     |
     v
resolve existing identity
     |
     +--> safe match ----> enrich existing knowledge
     +--> ambiguous -----> stop / clarify / preserve pending evidence
     `--> genuinely new -> create new identity
```

Similarity alone is never proof of identity. When evidence is insufficient, an explicit ambiguous or unresolved result is better than silent corruption.

### Human-readable knowledge stays authoritative

Canonical personal knowledge is Markdown owned by the user/workspace. SQLite indexes, embeddings, caches, model outputs, Git audit information, application views, and conversation transcripts may help Odyssey operate, but they do not replace the canonical knowledge.

The user should remain able to inspect, back up, synchronize, and use the Markdown independently of Odyssey.

Conversation context may help interpret an elliptical request such as “¿y dónde vive?”, but it must not silently promote old chat wording or assistant output into current personal truth. Current-fact answers remain grounded in canonical notes unless the user is explicitly asking about conversation history itself.

### Structure must earn its complexity

Odyssey does not maximize schema. A type or property is useful when it enables a repeatable capability such as filtering, comparison, calculation, reminders, analytics, or application behavior.

Ordinary facts stay ordinary facts when no such capability requires structure. Future applications may contribute validated domain structure without turning Core into one large business ontology.

The same test applies to product machinery: multiple chats, conversation indexing, summaries, extra model stages, routers, and background state should be added only when a concrete user need cannot be met cleanly by a smaller design.

### Safe automation behind bounded contracts

Models may interpret language and perform bounded semantic judgments, but deterministic code retains authority for schema validity, candidate identity, mutation scope, persistence, security boundaries, and fail-closed behavior.

Additional model stages and infrastructure are optimizations to justify with evidence, not product goals.

## Product surface

Odyssey is not tied to one chat product. A mobile/web client, ChatGPT, another assistant, or a domain application may consume the same Core knowledge through trusted integration boundaries.

The current product work is a minimal mobile web MVP so real usage can reveal which improvements are valuable before adding richer interfaces, collaboration, applications, or local/mobile runtimes.

The default conversational surface should remain simple: enough recent conversation context to let the user speak naturally, while the notes remain the actual memory and knowledge authority. Long-term conversation-history features should be introduced only when real use demonstrates that recent context is insufficient.

## Longer-term direction

Odyssey may become a persistent knowledge layer shared by multiple applications and authorized users while preserving private/local ownership where possible. Expected later capabilities include application composition, structured analytics, collaboration, bounded conversation context, product help, usage/cost observability, capture provenance, and proactive resurfacing.

Those directions should be implemented only from concrete use cases and security/data contracts. The [Functional Roadmap](architecture/functional-roadmap.md) owns implementation order; [Future Extension Points](architecture/future-extension-points.md) indexes intentionally deferred directions.
