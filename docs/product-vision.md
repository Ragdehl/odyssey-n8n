# Product Vision

Odyssey turns unstructured personal information into durable, reusable knowledge without making a
second system authoritative over the user's Markdown. The product should help a person capture,
connect, retrieve, and revise knowledge while keeping every stored result inspectable and portable.

## Product promise

- Accept information expressed naturally, including messages that mention several distinct things.
- Preserve one durable identity per entity, concept, person, place, project, or other knowledge item
  when the evidence supports that identity.
- Keep atomic or near-atomic Markdown notes as the source of truth and ordinary wikilinks as the
  default relationship representation.
- Prefer an explicit ambiguous or unresolved result over silently attaching facts to the wrong note.
- Keep automated reasoning behind deterministic contracts that can be tested, replaced, and audited.

```text
unstructured input
       |
       v
interpret and decompose
       |
       +--> new knowledge --------------------+
       |                                      |
       +--> references --> identity evidence -+--> validated Markdown
                              |
                        abstain when unsafe
```

## Responsibility boundaries

ChatGPT or another reasoning client may conduct the conversation. n8n owns integration and
workflow orchestration. `odyssey_core/` owns reusable domain, note, validation, identity, and
storage behavior. Markdown remains authoritative; derived indexes and local model artifacts remain
replaceable and rebuildable.

Odyssey should earn additional complexity through measured need. It does not need a general agent
framework, graph database, vector service, or new source of truth merely to anticipate future
scale. Local LLMs and other classifiers are implementation options, not product commitments.

## Identity-resolution safety

Incorrectly resolving a reference can corrupt otherwise valid personal knowledge. Resolution is
therefore layered: exact stored identity evidence first, candidate retrieval second, and contextual
decision-making only when measured evidence supports it. Candidate rank or similarity is never an
identity guarantee. A production contextual resolver must preserve three meaningful outcomes:
`RESOLVED`, `AMBIGUOUS`, and `UNRESOLVED`.

Phase 11A evaluated possible contextual decision technologies but did not implement the production
resolver. See [ADR 0002](decisions/0002-phase-11a-contextual-resolution-benchmark.md).
