# Development Pipeline

Odyssey evolves its development process only when a concrete problem justifies more machinery. GitHub, deterministic tests, bounded model evidence, and human review are the normal workflow; n8n is not the development CI orchestrator.

## Significant phase contract

Before implementing a significant functional phase, define at least:

- **Objective** — the user/system outcome and problem being solved;
- **Acceptance criteria** — observable evidence required for completion;
- **Out of scope** — nearby work intentionally excluded;
- **Open decisions** — unresolved choices, or `None`.

Then run `odyssey-architecture-challenge` against the contract and relevant repository context. This is a reasoning checkpoint, not a new state machine or project-management service.

## Architecture supersession and documentation coherence gate

When a user changes an approved architecture, **do not leave two competing
normative instructions** in the repo. Before treating the new direction as
an implementation task: (1) record the human decision in an ADR and one
canonical target contract; (2) update `AGENTS.md`, the functional roadmap and
the current overview; (3) search earlier contracts, phase logs, implementation
runbooks and decisions for conflicting **current/approved/must** wording;
(4) explicitly mark superseded contracts as historical while preserving their
measured results and immutable regression evidence; and (5) validate relative
links, target-versus-active DEV/PROD status and the named outstanding test
failures. Keep a short cross-document conflict audit for the next chat or
agent. A documentation target decision does **not** authorize changing
runtime behavior, model versions, personal data or deployment state.

For the Router change approved 2026-10-12, follow
[hybrid interpretation groups](router-hybrid-interpretation-contract.md)
and its [conflict audit](router-hybrid-documentation-audit-20261012.md),
not the older one-Core-call-per-atomic-fragment instructions.

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
  four-role audit at integration
             |
             v
 real-model E2E if model-facing
             |
             v
    honest readiness report
             |
             v
 human-approved merge/deploy
             |
             v
 authenticated published DEV E2E
             |
             v
        phase acceptance
```

### Default routing

| Work | Default executor | Reason |
| --- | --- | --- |
| Architecture/roadmap/status documentation | GitHub-capable agent | Direct, reviewable, normally no local execution needed |
| PR review / documentation coherence / architecture challenge | GitHub-capable agent | Cross-file judgment and independent review |
| Small deterministic, non-user-visible code change | GitHub-capable agent when focused CI gives sufficient evidence | Not a shortcut for model-facing/user E2E or integration audits |
| Broad multi-layer implementation/refactor/debugging | Codex | Local iteration materially improves reliability |
| Benchmark/harness or repeated experiments | Codex | Controlled execution/evidence collection required |
| Raspberry/Docker/filesystem/local-n8n work | Codex | Requires the actual environment |
| Final semantic review | GitHub-capable agent + human as needed | Independent gate before merge |

If a nominally small change becomes difficult to validate safely without local feedback, move it to Codex rather than stretching the GitHub path.

## Verification

**No silent waiver of acceptance gates:** deterministic CI, independent auditors and real-model browser E2E are separate evidence. A green CI proves offline contracts only. Before a model-facing user-visible integration is called ready, record a pinned-SHA real-model journey with browser UI, n8n, Core/E3, Markdown readback and retry. At coherent integration checkpoints, require fresh four-role audit receipts on the actual SHA, not a previous branch. Small documentation/static-only changes are not model-facing integration checkpoints. If credentials, actor isolation, cost authorization or access prevent a gate, its status is BLOCKED, never PASS; leave the phase unaccepted and label any merge/deploy as unaccepted. Deployed DEV acceptance additionally needs a genuine user session on the published app. The authority lives in AGENTS.md, odyssey-verify-change and odyssey-dev-e2e; do not describe cheaper substitutes as equivalent tests.

During implementation, run focused tests/checks. Before readiness, run `odyssey-verify-change` (or equivalent complete evidence when the local environment is unavailable) and require server-side CI.

**Commit-hook baseline repair (26 Oct 2026):** the historical unrestricted `pytest` hook collected 5,105 cases and failed 29 frozen prompt/snapshot and old operator-route checks on a schema source/skill-only change. The official `scripts/odyssey_cross_surface_gate.py` passed 2,180 Python + 233 JS on the same source. To prevent this recurring irrelevant commit blockade, the `pytest` hook now runs that **established active cross-surface gate** (and retains Ruff/schema hooks), not the entire historical archive. Raw `pytest` remains available for diagnosing old drift and the 29 failures are **not fixed or counted as PASS**. Future product changes must extend the official coverage where needed, and model/DEV browser/independent audits remain separate gates. Do not bypass a real failure of the active gate.

For production model-facing changes, deterministic checks are necessary but not sufficient; use the focused live evidence policy in `AGENTS.md` and [Testing Strategy](testing.md).

A failed gate means the branch is not ready. It does not require discarding coherent work; record a safe checkpoint when useful and continue/fix the blocker.

**Hosted-CI isolation tooling incident (23 October 2026).** The `dev` contract gate ran 1,957 Python tests successfully but failed three unrelated sandbox tests on the hosted runner: its image lacked both the native Codex CLI and `/usr/bin/bwrap`. The Codex *configuration-shape* test had unnecessarily required the real binary; it now substitutes a synthetic binary path for static config inspection, while the actual native isolation test remains conditional on CLI availability. Offline sandbox argument/workspace rejection now precedes the Bubblewrap availability guard, so invalid inputs are tested even without Bubblewrap; a valid request still fails closed without the isolator (covered by a new regression). Verify with both `pytest -q tests/runtime/test_codex_scoped_permissions.py tests/runtime/test_agent_offline_sandbox.py` and the full `scripts/odyssey_cross_surface_gate.py`; confirm the hosted GitHub check separately, not from a local green gate. Never bypass the isolation guard or treat skipped live native-kernel tests as a sandbox attestation.

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

## Real DEV contract-discovery loop

When deterministic tests are green but a synthetic/manual DEV request exposes a semantic miss, treat the request as a **boundary probe**, not as a reason to patch the visible symptom. The preferred loop is:

```text
exact user request on isolated DEV
        |
        v
record deployed commit + request/result + vault Git delta
        |
        v
trace adjacent boundaries until the first incorrect decision
        |
        v
challenge contract/oracle as well as implementation
        |
        v
smallest bounded fix
        |
        v
provider-free regression at the owning boundary
        |
        v
redeploy DEV + repeat the same request
        `--> fresh focused model gate only when model-facing contract changed
```

For WRITE/relationship work, inspect the actual canonical Markdown and Git delta before inferring what happened from the UI. A useful trace order is planner -> deterministic planner validation -> source/target candidate construction -> relation/fact selection -> contextual resolution -> preflight/dependency atomicity -> canonical rendering/materialization -> Git/index refresh -> UI projection. Incoming backlinks are part of canonical evidence when the contract says they are; derived indexes remain non-authoritative. A request that fails safely with zero vault mutation is evidence about a decision boundary, not permission to weaken that boundary.

Each real failure mode that reveals a durable invariant should become an executable regression, preferably abstracted from the incidental fixture wording. Keep a small number of exact phrases when they capture a model-facing contract that previously failed. Do not add retries to hide semantic ambiguity: retries are appropriate only for bounded structural/transient output failures. Core-only fixes do not require rerunning a planner gate; prompt/schema/structured-output changes do. Keep manual discovery in isolated synthetic DEV, preserve PROD, and use the resulting regressions so later feature work can move faster without rediscovering the same boundary.

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
