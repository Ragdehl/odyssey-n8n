# Product Vision

Odyssey turns fragments accumulated through life and work into durable, connected knowledge that the user, applications, and AI agents can safely return to and use.

Its enduring promise is:

> **Capture without friction, organize automatically, and retrieve the right information when it becomes useful.**

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

Canonical personal knowledge is Markdown owned by the user/workspace. SQLite indexes, embeddings, caches, model outputs, Git audit information, and application views may help Odyssey operate, but they do not replace the canonical knowledge.

The user should remain able to inspect, back up, synchronize, and use the Markdown independently of Odyssey.

### Structure must earn its complexity

Odyssey does not maximize schema. A type or property is useful when it enables a repeatable capability such as filtering, comparison, calculation, reminders, analytics, or application behavior.

Ordinary facts stay ordinary facts when no such capability requires structure. Future applications may contribute validated domain structure without turning Core into one large business ontology.

### Safe automation behind bounded contracts

Models may interpret language and perform bounded semantic judgments, but deterministic code retains authority for schema validity, candidate identity, mutation scope, persistence, security boundaries, and fail-closed behavior.

Additional model stages and infrastructure are optimizations to justify with evidence, not product goals.

## Product surface

Odyssey is not tied to one chat product. A mobile/web client, ChatGPT, another assistant, or a domain application may consume the same Core knowledge through trusted integration boundaries.

The current product work is a minimal mobile web MVP so real usage can reveal which improvements are valuable before adding richer interfaces, collaboration, applications, or local/mobile runtimes.

## Longer-term direction

Odyssey may become a persistent knowledge layer shared by multiple applications and authorized users while preserving private/local ownership where possible. Expected later capabilities include application composition, structured analytics, collaboration, bounded conversation context, product help, usage/cost observability, capture provenance, and proactive resurfacing.

Those directions should be implemented only from concrete use cases and security/data contracts. The [Functional Roadmap](architecture/functional-roadmap.md) owns implementation order; [Future Extension Points](architecture/future-extension-points.md) indexes intentionally deferred directions.
