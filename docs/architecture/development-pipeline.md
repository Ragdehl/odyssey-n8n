# Development Pipeline

Odyssey evolves its development process only when a concrete problem justifies more machinery. GitHub, deterministic tests, bounded model evidence, and human review are the normal workflow; n8n is not the development CI orchestrator.

## Significant phase contract

Before implementing a significant functional phase, define at least:

- **Objective** — the user/system outcome and problem being solved;
- **Acceptance criteria** — observable evidence required for completion;
- **Out of scope** — nearby work intentionally excluded;
- **Open decisions** — unresolved choices, or `None`.

Then run `odyssey-architecture-challenge` against the contract and relevant repository context. This is a reasoning checkpoint, not a new state machine or project-management service.

## Execution path

```text
phase/change contract
       |
       v
architecture challenge when significant
       |
       v
choose smallest reliable executor
       |
   +---+----------------+
   |                    |
   v                    v
GitHub-capable agent   Codex/local environment
bounded direct work   iterative/debug/environment work
   |                    |
   +---------+----------+
             |
             v
      Draft Pull Request
             |
             v
 deterministic CI + Sonar
             |
             v
       semantic review
             |
             v
         human merge
```

### Default routing

| Work | Default executor | Reason |
| --- | --- | --- |
| Architecture/roadmap/status documentation | GitHub-capable agent | Direct, reviewable, normally no local execution needed |
| PR review / documentation coherence / architecture challenge | GitHub-capable agent | Cross-file judgment and independent review |
| Small well-understood code change | GitHub-capable agent when CI gives sufficient validation | Avoid unnecessary delegation overhead |
| Broad multi-layer implementation/refactor/debugging | Codex | Local iteration materially improves reliability |
| Benchmark/harness or repeated experiments | Codex | Controlled execution/evidence collection required |
| Raspberry/Docker/filesystem/local-n8n work | Codex | Requires the actual environment |
| Final semantic review | GitHub-capable agent + human as needed | Independent gate before merge |

If a nominally small change becomes difficult to validate safely without local feedback, move it to Codex rather than stretching the GitHub path.

## Verification

During implementation, run focused tests/checks. Before readiness, run `odyssey-verify-change` (or equivalent complete evidence when the local environment is unavailable) and require server-side CI.

For production model-facing changes, deterministic checks are necessary but not sufficient; use the focused live evidence policy in `AGENTS.md` and [Testing Strategy](testing.md).

A failed gate means the branch is not ready. It does not require discarding coherent work; record a safe checkpoint when useful and continue/fix the blocker.

## Pull Request lifecycle

- Significant work normally starts/continues as a Draft PR.
- Before additional work on an open PR, inspect review feedback through `odyssey-pr-feedback`.
- Resolve deterministic and semantic blockers before marking Ready.
- Human merge only.
- After human merge, `odyssey-post-merge` may synchronize the local clone and clean only branches whose merge is confirmed.

The stable deterministic CI check name is `Python CI / Python deterministic checks`. Whether branch protection currently requires it is a GitHub repository setting and should be verified before relying on that enforcement. Protection/visibility/security settings are operational GitHub boundaries and must not be changed implicitly by repository code.

## Documentation lifecycle

The documentation structure intentionally separates current truth from historical evidence:

```text
README + product vision       product entry/durable promise
overview                      current architecture
functional-roadmap            current phase/status/order
thematic architecture docs    current durable contracts
future direction docs         intentionally deferred contracts
phase docs / ADRs / benchmarks historical contract/evidence
```

Rules:

1. One project fact/contract has one canonical current owner; other docs link rather than copy.
2. A phase document can preserve the wording/status of its checkpoint after completion. Do not keep manually updating every historical file to say what phase is now current.
3. The roadmap must not become a second copy of completed phase contracts; summarize and link.
4. Exact schema registry data lives in `config/note-schema.json`; prose explains semantics/ownership.
5. A future capability with a dedicated document should be indexed, not duplicated, in `future-extension-points.md`.
6. Do not create one Markdown document per workflow/function/benchmark when source/tests already carry the exact contract and a higher-level doc owns durable semantics.
7. Consolidation may remove obsolete/duplicated docs only after any still-useful rationale is preserved in a canonical contract, ADR, phase record, test, or benchmark.

This keeps documentation compact without throwing away the evidence needed to understand safety and architecture choices.

## Process evolution

Do not automate more of this pipeline until repeated manual friction demonstrates the need. Possible later experiments—independent automated reviewer, auto-merge policy, correction loops, automatic phase progression, notification/HITL routing, or a dedicated orchestrator—remain hypotheses, not commitments.
