---
name: odyssey-architecture-challenge
description: Challenge a significant new Odyssey functional phase before implementation to confirm the real problem, responsibility boundary, and simplest appropriate solution. Use before beginning a significant phase; do not use for tiny fixes, routine review feedback, formatting, typo-only documentation, routine test corrections, or post-merge cleanup.
---

# Odyssey Architecture Challenge

Act as a lightweight reasoning checkpoint, not an architecture service or redesign exercise.

## Workflow

1. Read the proposed phase contract and the repository context that materially affects it, including `AGENTS.md`, relevant architecture or decision documents, current code boundaries, and existing platform capabilities.
2. State the actual problem and intended outcome independently of the proposed implementation.
3. Challenge whether:
   - the problem and acceptance criteria are sufficiently understood;
   - the planned solution remains appropriate and is the simplest working option;
   - GitHub, Codex, pre-commit, n8n, Python, Markdown, storage, or another existing tool already owns or solves part of the responsibility;
   - responsibility is placed at the correct boundary;
   - the proposal adds accidental complexity, premature abstraction, duplicated responsibility, unnecessary coupling, or infrastructure without a demonstrated use case;
   - an earlier project decision should now be reconsidered because concrete evidence has changed.
4. Avoid constant redesign. Treat minor implementation choices as implementation work and default to the approved architecture when it still fits.
5. Return the result before implementation starts.

## Result

Return `PROCEED` when no material concern exists. Briefly record the reasoning when it helps implementation.

For a material concern, return exactly this structure:

```text
RECONSIDER

Material concern:
...

Simpler alternative:
...

Trade-offs:
...

Recommendation:
...

Human decision required: YES | NO
```

Set `Human decision required: YES` only for a genuinely material product behavior, source-of-truth, schema or ontology, major architecture, security or permission, significant infrastructure or service, destructive or difficult-to-reverse choice, or meaningful unresolved trade-off.

Set it to `NO` when the better solution is clearly implied by approved Odyssey architecture and can be adopted without a material decision.
