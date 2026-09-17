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

## Maintainability guard during feature work

Code quality is a continuous constraint, not a reason to stop useful product work for speculative cleanup.
Every significant architecture challenge and implementation review should include a small
maintainability pass before adding new abstractions or parallel code paths:

1. **Reuse before duplication.** Prefer an existing tested primitive, helper, repository, validator,
   or contract when it already owns the behavior. Do not copy a near-equivalent implementation into
   another capability merely to move faster locally.
2. **Factor only proven repetition.** Two superficially similar code paths may have different trust,
   data, or lifecycle boundaries. In particular, repeated validation at Core/runtime/integration/UI
   trust boundaries can be intentional and should not be collapsed merely to satisfy DRY.
3. **Keep coordinators coordinators.** A composition/orchestration file may dispatch work, but new
   domain lifecycle rules should live in the capability/Core component that owns them rather than
   accumulating as special-case branches in a central request function or n8n workflow.
4. **Watch change amplification.** If one small product behavior repeatedly requires equivalent edits
   in several unrelated files, or if tests need source-text assertions because no executable contract
   exists, treat that as evidence for a better shared boundary.
5. **Refactor with evidence.** Prefer bounded cleanup alongside or immediately after the feature that
   exposes the problem. A broad rewrite requires a concrete maintenance/testability benefit and the
   same deterministic verification as functional work.

Current post-UI-0 watchpoints are deliberately a **review list, not an immediate refactor mandate**:

- `odyssey_core/application.py` is still a useful request-level coordinator, but Tasks/Events/Projects
  should not turn it into a growing set of application-specific branches;
- `workflows/odyssey-online.ts` contains substantial embedded JavaScript for integration/product
  projection; new capabilities should keep n8n thin rather than moving domain semantics into those
  strings;
- `odyssey_web/app.js` / `client.js` are appropriately small for the present UI, but UI-2 and later
  capability surfaces should extract modules/components when responsibilities begin to mix;
- the UI-0 transition left legacy conversation code/tests beside the root-bound
  `LocalConversationStore`; retire or consolidate that historical path when compatibility evidence
  shows it is safe, rather than carrying two apparent conversation authorities indefinitely;
- historical names such as `experimental_luna_planning.py`, and source-string workflow assertions,
  are hygiene candidates when the surrounding area is next touched, but do not justify risky churn by
  themselves.

The planned product sequence intentionally takes priority over a standalone cleanup phase now:
**read-only Notes -> Tasks -> Events / Calendar (plus the Reminder behavior those capabilities
actually need)**. After that application/calendar path has exposed the real extension patterns,
perform a bounded maintainability checkpoint before substantial secondary-app expansion unless an
earlier feature exposes concrete pain that should be fixed locally. That checkpoint should remove
proven duplication/legacy, improve weak contract tests, and split genuine hotspots; it should not be a
rewrite or architecture reset.

The [Functional Roadmap](functional-roadmap.md) owns when that checkpoint sits in current sequencing.
This document owns the reusable maintainability discipline applied during every phase.

## Close the loop on incidents and debugging

A solved incident should reduce the cost of the next similar incident. After a non-trivial bug, deployment drift, hidden environment precondition, or operational failure is understood, close the loop before declaring the work complete.

Use this compact pattern:

```text
symptom / trigger
      |
      v
smallest failing boundary
      |
      v
root cause
      |
      v
bounded fix
      |
      v
post-fix verification
      |
      +--> executable guard when justified
      `--> durable canonical note/runbook otherwise
```

The durable record should normally contain only:

1. the symptom/trigger and affected boundary;
2. the confirmed root cause, not abandoned hypotheses;
3. the bounded corrective action;
4. the exact verification that proved recovery;
5. the cheapest preventive diagnostic or guard for recurrence;
6. rollback/safety notes when live data, credentials, networking, deployment, or security are involved.

Choose the canonical owner rather than creating an incident-document backlog: phase/benchmark docs preserve checkpoint evidence; infrastructure/runbooks own operational recovery; architecture/storage docs own durable invariants; future-direction docs own deferred improvements. Link between owners instead of duplicating the story.

When practical, promote the lesson from prose into a deterministic check: test, preflight assertion, deployment/source fingerprint check, health probe, explicit environment-root verification, or bounded runbook command. If the check is not worth automating yet, keep the manual verification step explicit.

For multi-layer failures, prefer boundary isolation over broad changes. Compare the same input at adjacent boundaries and eliminate healthy layers before changing prompts, models, infrastructure, or canonical data. Preserve the shortest successful isolation method when it will be reusable.

Never mark a live action complete merely because the intended command was issued. Record **observed post-change state** separately from intended/configured state and require explicit verification evidence.

## Pull Request lifecycle

- Significant work normally starts/continues as a Draft PR.
- Before additional work on an open PR, inspect review feedback through `odyssey-pr-feedback`.
- Resolve deterministic and semantic blockers before marking Ready.
- Human merge only.
- After human merge, `odyssey-post-merge` may synchronize the local clone and clean only branches whose merge is confirmed.

The stable deterministic CI check name is `Python CI / Python deterministic checks`. Whether branch protection currently requires it is a GitHub repository setting and should be verified before relying on that enforcement. Protection/visibility/security settings are operational GitHub boundaries and must not be changed implicitly by repository code.

## Production and development isolation

Once real users depend on Odyssey, ordinary development must not execute against the same public deployment, live workflows, or personal-data boundary as production. Maintain a stable production deployment and a separate development/staging deployment for feature testing before promotion.

The default branch model should remain as simple as possible:

```text
feature branch / PR
        |
        v
development or staging deployment
        |
   tests + human validation
        |
        v
      main
        |
        v
production deployment used by real users
```

`main` should represent the production-ready source. Feature branches may feed the development/staging environment. Do not introduce a permanent `develop` branch merely by convention; add one only if repeated parallel integration work demonstrates that a long-lived integration branch is materially useful.

Production and development must use separate mutable/runtime boundaries wherever sharing could allow a test to affect users or personal knowledge. At minimum, deployment planning must explicitly review hostname/routing, n8n workflow activation, environment/configuration, runtime state, provider credentials/telemetry attribution, and vault/data targets. Development evidence should use disposable/non-personal data by default. Promotion to production remains an explicit deployment action after merge and validation; merging source code alone must not silently mutate production data or security boundaries.

The production promotion boundary is `odyssey-prod prepare FULL_SHA` followed by independent
environment provisioning and `odyssey-prod deploy FULL_SHA`. It materializes and records only the
explicit 40-character commit in the dedicated `/home/ragdehl/projects/odyssey-prod-release` Git
worktree, then restarts only the production runtime service after health verification. Mutable refs
such as `main`, tags, and short SHAs are rejected. The normal
working repository may be dirty, staged, detached, or on another branch; it is never cleaned,
reset, checked out, restored, or used as the runtime source. Merging `main` makes a commit available
but does not deploy it. The release worktree is a controlled operational target and must be changed
only by an explicit promotion action. The rollback/control operator remains outside the candidate
release and is promoted only after health succeeds.

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
