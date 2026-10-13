# Odyssey agent instructions

## Goal

Odyssey turns unstructured personal information into durable, reusable knowledge. Canonical personal knowledge remains human-readable Markdown; automation should make capture and retrieval easier without replacing the user's files with a second authority.

A single request may retrieve knowledge, create or update several notes, resolve references, or combine reads and writes. Preserve stable identity and fail closed when identity or mutation authority is ambiguous.

## Current architecture

```text
external client
     |
     v
n8n integration/orchestration
     |
     v
thin Odyssey runtime
     |
     v
odyssey_core/
     |
     +--> canonical Markdown in /data/odyssey/vault
     +--> durable non-knowledge state in /data/odyssey/state
     `--> rebuildable runtime/index state in /data/odyssey/runtime
```

The current standalone consumer source lives under `odyssey_web/` as part of Phase 20. ChatGPT or other clients may also consume Odyssey, but no client owns the knowledge semantics.

- `odyssey_core/` owns domain, note, identity, planning, retrieval, validation, and mutation behavior.
- `workflows/` owns n8n integration/orchestration definitions.
- Markdown is authoritative personal knowledge.
- SQLite/indexes/embeddings/caches are derived and rebuildable.
- `config/note-schema.json` is the machine-readable canonical schema.
- n8n, browser code, and model providers must not become alternate semantic authorities.

### Application specialization invariant

Applications are narrow domain interpreters/executors, never miniature copies of Core. An application planner may emit only the minimum app-owned interpretation or operation needed for its specialty. When the remaining request uses shared Odyssey semantics, the app must return the exact routed source plus bounded Core-owned `DomainInterpretation` evidence and let the ordinary Core planner decide semantic ownership, targets, identities, references, facts, cardinality, mutation intent, and validation. Applications must not construct `RequestPlan`, `SemanticWriteIntent`, Core selections/candidate scopes, note types, generic properties/tags, Markdown, persistence instructions, or shared identity-resolution logic. App-owned direct operations such as a Calendar Day capture may execute through a narrow Core persistence boundary, but shared planning and mechanics stay in Core. Apps may depend on Core contracts; `odyssey_core/` must never import `odyssey_apps/`. Apply this invariant to every current and future application, including Calendar and Tasks.

Do not introduce LangGraph, a vector service, graph database, queue, additional application server, or other infrastructure unless a concrete requirement cannot be handled cleanly by the current boundaries.

## Local-first ownership boundary

Odyssey's target product is local-first. One user's Odyssey instance owns that user's local vault and durable local state. In hosted or server-backed deployments, authenticated identity should select the isolated user-local vault/state root; once that root is selected, inner local repositories should normally be root-bound rather than redundantly modeling multiple users in their physical storage layout.

Future local/mobile clients should be able to reuse the same local storage semantics without requiring server-style multi-user partitioning. Multi-user identity, permissions, groups, and synchronization belong to the separate collaboration boundary used when knowledge crosses a sharing boundary. Private local-only knowledge or state must not become centrally hosted merely because collaboration exists.

Current DEV/server actor isolation must remain enforced at the outer authentication/root-selection boundary; local-first storage is not permission to weaken current isolation. See [Odyssey Platform Direction](docs/architecture/odyssey-platform-direction.md) and [Multi-user Collaboration Direction](docs/architecture/multi-user-collaboration-direction.md) for the durable product direction.

### Clean Architecture incremental, diferida (13-10-2026)

Decisión del usuario: al modificar módulos en el futuro, aprovechar para
introducir límites claros entre dominio, casos de uso, puertos y adaptadores
de forma gradual. NO hacer ahora una refactorización global ni frenar DEV.
Consultar docs/architecture/clean-architecture-incremental-direction.md.
Mantener como contrato funcional el híbrido ya aprobado.

## Continuidad obligatoria entre chats/agentes (13-10-2026)

Para trabajo sobre la arquitectura híbrida y nuevas aplicaciones, **antes de implementar o proponer el siguiente paso**, leer [seguimiento activo del Functional Roadmap](docs/architecture/functional-roadmap.md) y [plan de continuidad y extensibilidad](docs/architecture/application-extensibility-plan.md). El roadmap tiene el **único estado actualizado** de etapa, siguiente acción, evidencia, rama y DEV/PROD. El plan detalla objetivos, secuencia, contratos y criterios de aceptación. Comprobar el worktree y la realidad del runtime con Git/inspección; no confundir commits, pruebas aisladas y despliegue. Al terminar cada paso sustancial, actualizar en el mismo cambio el roadmap con qué se hizo, qué falta, pruebas, commit/PR, estado operativo y próximo paso, antes de cerrar el chat. No depender de la memoria de ChatGPT ni pedir al usuario reconstruir lo ya documentado. Esta regla complementa la propiedad documental y los gates de seguridad de abajo; no autoriza deploy, merge ni cambio de datos.

## Development principles

### 2026-10-13 — LATEST hybrid status: 25 completed + 2 safe pending

Older 23/27 and 24/27 counts below are historical. F09 now passes:
two independent genuine GPT-5.6 semantic equivalence reviews confirm
Marta already has the complete Lyon fact, so her canonical Note is
unchanged. Luis receives the new fact. Current-note identity, content
hash and exact supporting quote are checked before a skip and again
during readback. Semantic review is optional, read-only, provider store
disabled, and bounded: long Notes remain writable, no truncated
existing context is allowed to certify an already-known fact.

F14/F27 already persist their independently proven prior conversation
facts. The new opt-in hybrid pending boundary now also stores their exact
original cinema source clause with captured date, reference and options
Eric/Luis proven by the previous Core-linked persisted fact. It does
NOT resolve "él" itself: it requires a user choice. The actual pending
v2 workflow and guarded subsequent Core continuation ("Con Luis") are
covered by deterministic replay of genuine Router/Temporal/Planner and
independent reviewer outputs. No second invented Person or Day fact.
If the callback is unavailable, source cannot be scoped, options change
or proof goes stale, never promote a candidate identity.
More than four plausible people may be kept as source-only pending,
not a misleading truncated choice list.

The strict score is therefore 25/27 fully completed; the other two
are correctly handled as durable pending clarification, NOT magically
fully resolved. This capability is not yet deployed in DEV or PROD.
When activating hybrid in DEV, wire the route ambiguity recorder to
authenticated per-conversation v2 Pending state and display choices in
the chat; do not claim live app support before then.

Evidence: benchmarks/application_router/hybrid_known_fact_v1/F09.json;
tests/runtime/test_hybrid_known_fact_real_review_20261013.py;
tests/runtime/test_hybrid_ambiguous_real_pending_20261013.py.
Last full-suite results on 2026-10-13: 3039 passed, 80 skipped,
the same 10 historical dated/version-hash failures; no new regressions.
Continue incremental Clean Architecture only when touching modules
for functional work, never a wholesale rewrite during DEV preparation.

### Regression memory for real chat failures

When a real Odyssey chat interaction reveals a new semantic failure mode, preserve that exact case as
a deterministic regression sentinel before considering the fix complete. If the failure depends on
LLM interpretation or prompt behavior, also run the smallest relevant live Luna check during the
change when credentials are available; keep deterministic tests as the CI authority so provider
variance never weakens the gate. Generalize the regression with additional note types or equivalent
shapes when the product invariant is type-generic. Do not remove or relax an accepted real-chat
sentinel merely to make a later prompt or architecture change pass.

### 2026-10-13 — Mandatory cross-boundary DEV observability and post-write gate

A passing backend write/read test is NOT enough to authorize manual DEV chat
testing. Any changed Core telemetry field or execution flow must be checked
through the generated n8n response contract AND the browser validator/graph;
unknown optional diagnostic metrics must never erase otherwise valid stages,
costs, or write outcomes. Assert real hybrid lifecycle progress events using
the authenticated progress store rather than assuming the donut advances.
When an error occurs after a physical canonical write, retain the verified
Core write receipt and affected note IDs, disclose partial completion and
block unsafe dependent handoff; do not convert it into an apparent zero-write
failure or retry using a new delivery ID. For each real user-chat regression,
record exact source/result and a provider-free crossing-boundary sentinel,
and make a bounded DEV E2E smoke (stages, flow, progress, readback) a deployment
acceptance check. See the active functional roadmap for the 13-Oct findings.

### 2026-10-13 — Auditoria exhaustiva de formas y casos pendientes

Consultar docs/architecture/hybrid-source-validator-audit-20261013.md.
La arquitectura hibrida usa evidencia fuente 1..N y nunca plantillas
espanolas de dos nombres/conversaciones. F22 completo funciona en
replay real con tres Tasks y enlaces canonicos; nuevo conteo 24/27.
F09 sigue NO ACEPTADO por duplicacion semantica de Marta aunque el
WRITE informe COMPLETED. F14/F27 conservan partes correctas y
no resuelven el pronombre ambiguo el por cercania.
Priorizar contrato Core semantico de ya representado con readback
canonicamente verificado. NO parchear nombres ni verbos de ejemplos.

### 2026-10-13 — Hybrid validator generalization (implemented, feature branch)

The previous Spanish phrase-template pilot in
odyssey_core/candidate_sequential_contacts.py is **LEGACY ONLY**. Hybrid
Core may NEVER dispatch through it: multi-fact participant coverage now
checks each independently reviewed candidate/fact using explicit source
participants, independently proven inheritance, unique canonical reference
helpers and the ordinary Writer. No fixed name, two-contact phrase, or
three-unit Action topology may be introduced as a hybrid rule.

The independent graph reviewer now permits a slightly longer ORIGINAL
source quote around a verified Router anchor (e.g. one preposition), but
NEVER a fabricated quote, and all other Core prewrite checks remain.
F01 now completes three dated group events in two Day Notes with real
model/reviewer and physical readback.

F02 mixed exact/approximate Temporal interpretation is supported only
when Temporal's UNSPECIFIED wording exactly matches an original Router
time_approx span. It stays a literal approximate phrase, never a clock;
exact independent days/clocks still pass with per-fact coverage. Same-Day
redundant date-reference parts are removed before the normal compiler
and Writer, never guessed or emitted as self-links.

Current **strict isolated-genuine-model corpus checkpoint: 23/27**:
F01 F02 F03 F04 F05 F06 F07 F08 F10 F11 F12 F13 F15 F16 F17
F18 F19 F20 F21 F23 F24 F25 F26. Remaining F09 (redundant/canonical
semantic delta), F14/F27 (truly ambiguous subject pronouns: safe partial),
and F22 (Task body omits known person link). F02 results captured in
benchmarks/application_router/hybrid_approximate_live_v2 and
hybrid_core_review_v4, final F01 in hybrid_core_review_v3.
**Estimated cumulative experiment spend USD 0.64794381 of 1.00 authorized,
not billing reconciliation.** No activation in DEV/PROD and no user-vault
writes. Frozen original captures remain immutable. This checkpoint
supersedes older counts but not their historical test records.

One limitation remains separate: the read-only experimental known-Note
hint lookup currently refuses to scan vaults larger than 5000 Notes and
only returns 16 prompt hints. This is a performance guard, **not** a
permitted semantic limit on Odyssey's Note or fact count. Replace with an
indexed, bounded-retrieval implementation before broad DEV adoption;
never silently treat a too-large vault as evidence that a named Note
does not exist. Similarly audit historical narrow validators instead
of copying their grammar templates.

### Generality invariant for Router and Core

A Router candidate is an untrusted description of part of the ORIGINAL
message, **not** a Core fact, Note, request or write action. One user
message may contain a variable number of candidates; one candidate can
produce zero, one or several Core facts, and several candidates can
contribute to one fact. Do not translate candidate ordinals into Core
write ordinals or require an arbitrary fixed number of candidates,
participants, predicates or actions. Technical limits on provider bytes,
source size and model context must be explicit budgets; they are not
semantic rules and must not silently discard surplus information.

### Approved Router hybrid interpretation target (2026-10-12)

**The target architecture is HYBRID and is not yet active in DEV/PROD.**
Read the [single normative target contract](docs/architecture/router-hybrid-interpretation-contract.md)
and [accepted ADR 0010](docs/decisions/0010-router-hybrid-interpretation-groups.md)
before modifying Router/Temporal/Core/Writer. These supersede the previous
2026-10-11 **mandatory per-atomic-fragment Core interpretation** guidance.
The earlier [unit-dispatch experiment](docs/architecture/router-unit-dispatch-contract.md)
and [fact-candidate development log](docs/architecture/router-fact-units-v1.md)
retain historical evidence and working fallback implementations, but they are
**not the normative target** where they disagree about grouping.

Router receives the complete current message ONCE and identifies source-anchored
**atomic candidate facts/actions**, relevant grammatical roles, negation,
conditional scope, dates/times and typed source dependencies. Candidates are
untrusted linguistic hypotheses, never Core facts, canonical identities,
Note types, mutation plans or execution authority. The compiler constructs
**bounded exact-original-source interpretation groups**: keep semantically
interdependent facts together when splitting would lose a common actor,
predicate, shared/postposed time, correction, negative/conditional scope or
ellipsis; keep independently meaningful actions in separate groups even if
they share a date or person. Grouping is not one fact, one Note, one WRITE,
or an instruction to join unrelated message topics. Do not branch on names,
test IDs, punctuation or a fixed number of candidates.

Temporal interprets the selected group when it has date/time language and
returns grounded date/time ownership **for its individual claims**. Core's
ordinary Planner (remain on GPT-5.6 for this phase) interprets only its
selected group plus bounded, validated relevant context. It may plan zero,
one or several facts, identities and destinations for that group, subject
to an independent Core-owned exhaustive candidate↔fact review (including
N:M mappings and explicit pending candidates). Core/Writer verify **each**
fact's actual target and safe mutation/readback; an uncertain claim cannot
silently disappear or force an ungrounded write. Safe independent successes
may persist only where ordinary Core boundaries prove partial-write
isolation and idempotence. The full original source stays read-only
provenance, NOT a new Core planning prompt for unrelated sibling groups.

Source-level shared words/date/subject *within* one interpretation group
do not require a previously persisted sibling fact as proof of syntax.
Across groups, rely only on validated typed source/date context and, when
the dependency is on canonical identity or an already written event,
freshness-checked **Core-authored** identity/event evidence, including
canonical Markdown readback guards. Lexical Router hints do not authorize
canonical links or copying another actor's facts. Unknown, ambiguous,
stale, contradictory, approximate or unsafe interpretations remain
pending/fail closed, including negative and conditional occurrences and
ambiguous pronouns. No automatic promotion of a repair need to a Task.

**Latest hybrid feature-branch checkpoint (2026-10-12):** The ORIGINAL
five-case grouped live pilot completed only F04/F16 (2/5), with F03/F23
Core pending and F21 Temporal blocked. Subsequent narrow source-safe
adapters, real-model tests and Markdown readback have now completed
F03/F21/F23 too, on copied synthetic Notes only. Frozen success captures
live in `benchmarks/application_router/hybrid_grouped_v2/`; the original
failures in `hybrid_grouped_v1/` remain historically accurate. F03 may
retain unverified complete-set wording such as `mis hijos` LITERALLY; it
must never invent member identities. F21 uses independently verified
Temporal exact weekdays plus one unambiguous shared source clock. F23
writes reference-free literal component names to ONE canonical project
Note when real component identity cannot be verified. These are narrowly
bounded positive examples, NOT universal language or canonical-link proof.

**Subsequent sensitive-scope checkpoint (2026-10-12):** Fresh model
attempts on F17 (joint negation), F19 (corrected plan), F20
(conditionals), F18 (mixed negation/affirmation) and F22 (independent
tasks) remain **not fully supported**. Their real replies are frozen
in `benchmarks/application_router/hybrid_sensitive_v1/` and replayed
through copied Notes. Negations, cancelled events, and conditional
branches stay pending/fail closed rather than becoming affirmative
occurrences. F18 has two separate pending routes; F14 remains ambiguous
and F27 has an invalid source dependency. F22 originally saved its
last intent as a plain Day fact, NOT a Task; the new **opt-in hybrid**
Task safety gate rejects ordinary WriteActions for task candidates until
a real Tasks capability and lifecycle are reviewed. The old atomic mode
retains its historical behaviour. F25 repair-need must not silently
become a Task. **No broad task, negation, correction or conditional
write capability is claimed by these safety tests.**

**Latest source-preserving sensitive-scope checkpoint (2026-10-12):**
The EARLIER F17/F20 NEEDS_ATTENTION results in
`hybrid_sensitive_v1/` are historical. After implementing the typed
`verified_sensitive_temporal` gate and the strict
`candidate_sensitive_statement.py` whole-source validator, F17
(shared negation) and F20 (mutually exclusive weather conditions) now
both **COMPLETED** with fresh genuine GPT-6 Temporal, GPT-5.6 Core and
independent graph reviewer. The Writer read back **one EXACT original
literal statement per Day Note**, with no inferred occurrence, guessed
person link, condition deletion, or extra fact. Real outputs frozen in
`benchmarks/application_router/hybrid_sensitive_literal_v1/`; replay
without new provider calls in
`tests/runtime/test_hybrid_sensitive_literal_real_replay.py`.
This supports only **two-candidate same-Day positive-source-form
literal statements** preserving their original negation/condition,
NOT arbitrary counterfactuals, event creation or confirmed visits.
F18 (one negative plus one positive in independent groups) is still
pending subject/date evidence.

A separate fresh GPT-6 Tasks + GPT-6 Temporal + GPT-5.6 Core probe of
F22's **THIRD FRAGMENT ONLY**, `mañana preparar la factura`, created
one real Tasks Note on a disposable vault: `type: task`,
`status: pending`, target_date `2026-10-05` per fixture clock,
through the actual Tasks Core Planner and TaskLifecycleGuard. Its
immutable provider results live in
`benchmarks/application_router/hybrid_tasks_v1/F22-last.json`; a
hybrid dispatcher end-to-end replay deliberately leaves the other
two source tasks pending. This is **NOT** three-task F22 success,
nor DEV/PROD app integration. Approx cumulative authorized-test spend
USD **0.3356791 of USD 0.50** (estimate).

**Current original corpus acceptance (2026-10-12; fresh grouped
source-review live gates):** **10/27** strictly accepted: F03 F04 F06
F11 F16 F17 F19 F20 F21 F23. All 18 previously unaccepted non-F22
cases were run with real models, and six have fresh source-review
model trials. The original six-case genuine receipts are frozen in
`benchmarks/application_router/hybrid_source_review_v1/` alongside
the all-18 batch
`benchmarks/application_router/hybrid_live_matrix_20261012/`; the
small controlled budget-refusal F07 retest is frozen in
`benchmarks/application_router/hybrid_temporal_reference_v1/`.
The normative per-case readback and accepted-vs-functional distinction
are documented in `docs/architecture/functional-roadmap.md`.
Estimated cumulative approved model spend USD **0.471058 / 0.50**.
**Newer 2026-10-13 all-real-model checkpoint supersedes the above
10/27 acceptance COUNT, not its frozen historical evidence:** strict
**18/27** accepted on isolated versioned synthetic Markdown:
F03 F04 F05 F06 F07 F08 F10 F11 F12 F13 F15 F16 F17 F19 F20 F21
F23 F24. Earlier 10/27 results remain immutable snapshots.
Seven new authentic all-component receipts plus one frozen genuine
Planner/Temporal/Router + fresh genuine reviewer gate are preserved under
`benchmarks/application_router/hybrid_semantic_live_v2/` through `v7/`
and `hybrid_core_review_v1/`. The final F05/F08 pair uses authentic,
source-matched frozen Router/Temporal/Planner outputs with newly paid
GPT-5.6 independent reviews of the ACTUAL final fact text. The NoteSchema
v3 types were reviewed directly: concept, project, document, person,
calendar_day and non-writable legacy journal_entry; Tasks is an app
extension, not a core note type. All outputs are from a disposable
13-note versioned vault, never /data/odyssey. Estimated cumulative cost
USD **0.59769438 / 1.00** authorized, estimate only. No DEV/PROD
activation or migration. Remaining F01 F02 F09 F14 F18 F22 F25 F26 F27
require further honest semantic/provenance review; F14's pronoun is
genuinely ambiguous and must stay pending, not forced into an acceptance.

What changed in general: hybrid-only Core prompts for source-group
ellipsis, correct sentence composition and exact Temporal pairs; Core
read-only exact named-note hints (no speaker/group identity inference);
read-only typed Temporal evidence reaching the independent fact reviewer;
source-proven time co-reference no longer masquerades as a canonical
person reference; source-verified independent linked Day events,
separate named linked write units, mixed-type property+event facts, and
canonical Markdown fact readback. Retain all historical prompt/snapshot
contracts in non-hybrid mode. New changes need the full pytest baseline
and the versioned real-model replay before activation.

F13 now writes all correct facts but leaves a stray leading period in
one Markdown fact IN THE EARLIER ORIGINAL CAPTURE; its newest genuine
model result no longer has that punctuation error. F14 correctly
writes the safe Eric/Luis conversation but leaves the later genuinely
ambiguous pronoun pending. F07 has a provenance-safe grouped-note replay,
but the latest fresh Planner supplied a Temporal text superset and was
rejected; the next experimental attempt hit a *local conservative
budget gate* before Planner, not an OpenAI outage. No DEV/PROD, n8n or
real Notes changes. Never infer semantic or product acceptance solely
from dispatcher COMPLETED. Do not infer authenticated `yo=Alex`
from the seeded fixture's family links.

**Scoped Tasks interpreter checkpoint (2026-10-12):** The opt-in Tasks
surface now has a separate `interpret_scoped` contract for a route holding
trusted `TaskScopedEvidence`. It preserves the ordinary legacy
interpretation schema, parser, prompt and frozen responses unchanged. The
new strict schema adds only bounded `{reference_index, role}` selections over
the passed exact Temporal references; the model cannot propose a date, turn
external text into a local mention, select a Work Session operation, choose a
Task identity or mutate. Parsing/composition reject unknown/out-of-range or
duplicate selections, local set/clear conflicts, unsupported roles and exact
date/date-time incompatibility. A sidecar maps selected proof to
current-fragment Task property evidence plus exactly the selected inherited
references for Core. Strict fake-provider wire tests and a three-Task
synthetic Markdown replay exercise this path; **no new provider call was
made**, the whole F22 case remains PARTIAL, and the 27-message score is
unchanged. A focused live Tasks gate remains required before claiming model
acceptance or considering DEV/PROD activation.

**Further opt-in implementation checkpoint (2026-10-12):** F19 now has
`odyssey_core/candidate_corrected_plan.py`: the first occurrence is
source-proven superseded, and only the replacement FUTURE INTENTION may
be written with an exact Temporal date/clock and independent Core reviewer.
Core records `superseded_by_correction` as resolved (not an outstanding
user request) **only** when the corrected fact is actually independently
reviewed and planned; unsafe/missing final evidence still fails closed.
Three immutable genuine model captures in
`benchmarks/application_router/hybrid_correction_v1/F19.json` reproduce
2 historical pre-fix blocks and 1 now-completed final plan with real
Writer/Markdown readback. This is a bounded corrected-plan shape, NOT
universal negation/conditional handling.

For Tasks, the hybrid source compiler optionally routes only pure task
groups to registered `tasks` using explicit `enable_tasks=True`; the
scoped executor requires an injected trusted Tasks executor, with NO
Core/Day fallback on unavailable Tasks. `TaskCorePlanner` plus
`TaskLifecycleGuard(CREATE)` have been exercised with a real canonical
Task Note and status `pending` in a disposable test vault. This was a
**deterministic** application integration, not a fresh live Tasks model
end-to-end success. The legacy default compiler/DEV/PROD remain unchanged;
mixed property+repair requests do not automatically create Tasks.

Continue the frozen 27-message corpus, semantic/negative/conditional,
partial-write and prompt-gate testing before promotion. Existing v0 route
behavior, deferred model-version migration and active DEV/PROD must not
be rewritten or described as already migrated. The feature-branch code
is opt-in only; documentation adoption grants no merge/deployment approval.

**Never implement a linguistic failure by branching on a specific user
phrase, name, pronoun, conjunction or benchmark ID.** Preserve such cases
as tests, then identify the general invariant they expose. If a feature
requires a narrowly bounded pilot, isolate and label it explicitly,
do not accumulate production-facing infrastructure on that restriction,
and do not present its passing tests as general-language coverage.
Before accepting changes to this flow, test independently chosen source
shapes and candidate counts (including 1, 3, 5 and larger); verify both
the source-to-plan cardinality and canonical readback without treating
syntactic overlap as semantic proof. Unknown or unverified mappings must
remain pending or fail closed rather than using a shortcut that weakens
Core's identity or write checks.

### Stable whole-message regression corpus invariant

For Router/Temporal/Core/Writer behavioral work, always run the versioned
original-message corpus together with an isolated copy of the committed
canonical synthetic-note fixture in `tests/fixtures/full_message_corpus_v1/`.
A regression test must not change, seed or read the actual user's vault.
Tests for existing entities and links must validate persisted Markdown,
canonical identities and backlinks in a fresh disposable vault; preserve
negative/pending outcomes. When a new real chat failure arrives, preserve
its original message and the necessary fictional canonical Notes in a
versioned successor fixture, then replay it after every relevant change.
Keep saved authentic provider outputs and deterministic SDK-shaped tests
clearly separated from *fresh live* model evidence; green replay does not
mean 27 live model passes. Never change production interpretation for a
specific test case or guess candidate-to-fact links to make the corpus green.

### Human-approved singular identity creation invariant

For WRITE, when semantic planning classifies a mention as one singular identity with a canonical
`note_type`, failure to ground that identity does **not** turn it into literal text. Preserve the
ordinary typed identity lifecycle: resolve/reuse an existing canonical identity when safe; if no
identity resolves and there is genuinely no conflicting evidence, Core may CREATE the typed note.
This applies whether the singular identity was described directly or through a `one_member`
candidate scope.

Literal fallback is reserved for wording that denotes a true `complete_set`/group when no complete
canonical member set can be grounded; Odyssey must not invent a placeholder entity for that group.
Ambiguous, incomplete, stale, or contradictory evidence remains fail-closed and must never be
converted into CREATE or literal fallback merely to make the write succeed.

This is an explicit human-approved product invariant, not an implementation convenience. Any future
proposal that would make a singular typed identity become literal text, or remove its ordinary
CREATE authority solely because grounding failed, is a material product-contract change. **Stop and
ask the human before implementing it, and explicitly state that the proposal conflicts with this
accepted invariant.** Keep deterministic regression sentinels for both the singular CREATE behavior
and the complete-set literal fallback.

- Prefer the simplest working solution and challenge unnecessary complexity.
- Understand the user-visible requirement before optimizing implementation details.
- Keep changes small, reviewable, and testable; avoid unrelated edits.
- Put Odyssey knowledge/domain logic in `odyssey_core/` by default and integration/orchestration in `workflows/`.
- Prefer native n8n behavior when it solves an integration problem cleanly; use custom code when it gives a clear contract or safety advantage.
- Reusable workflows/subworkflows should expose narrow, explicit input/output contracts and hide implementation details from callers.
- When architecture, workflow, or component interactions are easier to understand visually, use a concise text/ASCII diagram; omit decorative or redundant diagrams.
- Keep components replaceable behind explicit contracts.
- Never silently change the ontology/schema. Material schema changes require an explicit proposal, compatibility/migration review, deterministic validation, and normally human approval.
- Never expose, print, commit, or persist credentials/secrets in project files or documentation.
- For an explicitly authorized one-shot live gate that needs `/home/ragdehl/.config/odyssey/secrets.env`, prefer a transient `systemd --user` unit with `EnvironmentFile=` and `--wait --collect --pipe`. Pass only the gate authorization flag explicitly; never source or print the secret in the remote shell, copy it into tmux, or persist it in the repo. If the user service manager or fixed environment file is unavailable, stop before provider access and ask the human operator rather than inventing another credential path.
- A plain Remote Desktop terminal deliberately has no `OPENAI_API_KEY`.
  **Do not infer a provider outage or ask for a new key from that fact.**
  First check the EXISTING fixed secrets EnvironmentFile and user systemd
  manager. On this Pi the manager may need `XDG_RUNTIME_DIR=/run/user/1000`
  and `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`.
  Authenticate using only an ephemeral unit, never printing credentials,
  and honor approved budget flags for all billable provider calls.
- Explain material architecture/security/data trade-offs before changing those boundaries.
- Do not delete or overwrite real personal knowledge as part of development evidence.

Production Python is for human readers. Functions and methods must have useful functional docstrings describing domain responsibility, parameters, returns when relevant, and meaningful errors. Add concise comments/examples only where behavior or safety reasoning is not obvious; do not narrate syntax.

Ruff is the Python lint/format authority and pytest is the Python test runner. Preserve existing unittest tests unless functional work already makes migration useful.

Every functional behavior change must ship with both **focused unit/contract tests** and **vertical end-to-end regression coverage** for the affected user path. The end-to-end layer must exercise the real production boundaries as far as safely possible (for example Router → application planner → runtime → Core/persistence) while replacing only external providers, credentials, or real personal data with deterministic fakes/isolated fixtures. Keep these tests as future regression sentinels. If a true vertical path cannot yet be exercised, document why and add the closest integration test before declaring the change ready; unit tests alone are never sufficient evidence for a functional change.

## Model-facing changes

Prompt evolution is inheritance-first. When introducing a model-specific, cheaper-model, experimental, or revised prompt for an existing capability/contract, start from the strongest existing validated prompt for that same behavior. Preserve established safety, semantic, and edge-case instructions by default; improve or adapt them rather than silently recreating the prompt from scratch. Any deliberate omission or simplification must be explicitly diffed, justified, and covered by regression sentinels before live evaluation. Model-specific wording may be shortened or reorganized, but previously validated behavior must not be dropped accidentally.

A deterministic test cannot prove that a production model follows a changed prompt or structured-output instruction.

Whenever a production LLM prompt, model-facing instruction, or structured-output contract changes materially:

1. keep deterministic schema/fail-closed tests throughout development;
2. include a compact regression-sentinel set for prior behavior the change could disturb;
3. reuse frozen cases/oracles where possible rather than rerunning unrelated model selection;
4. once the functionality and candidate contract are otherwise settled, run one focused live evidence gate with the same production model and reasoning configuration before readiness/merge;
5. if provider access is unavailable at that final gate, report the missing live evidence explicitly instead of treating the change as validated.

For Odyssey planner changes, preserve the last accepted model-facing contract by hash (rendered Luna prompt, provider schema, teaching examples, production model, and reasoning effort), but do not make ordinary intermediate CI fail solely because an in-progress candidate differs from those hashes. The exact current-versus-accepted hash check is a final pre-merge gate, run once after deterministic feature validation. If any protected value still differs then, do not update the accepted hash merely to make the gate green: prepare a fresh versioned live regression gate, keep it at zero provider authority until explicit bounded cost approval, collect the complete frozen matrix, and update the accepted contract only after the evidence is reviewed. Do not repeat provider gates for every intermediate prompt edit. New model evaluations start with GPT-6 Luna when applicable; if the production model is different, the production configuration must still pass its focused regression gate unless the human explicitly approves a model switch backed by its own evidence.

For user-visible clarification or continuation changes, deterministic tests must cover the affected flow vertically rather than only testing isolated functions. Cover every meaningful state transition for the changed workflow (initial clarification, candidate choice, cancellation, unresolved free text, unrelated new request, stale target evidence, stale source evidence, replay/idempotence, and generic non-person Note types when applicable). Provider live gates supplement these tests; they do not replace them.

Before changing a prompt because a sentinel failed, determine whether the model regressed or the oracle is over-constrained.

## Development autonomy and confirmation

On a feature branch, proceed autonomously with routine, reversible, in-scope work: repository edits, tests, validators, isolated disposable fixtures, development/test n8n executions, review fixes, commits/pushes, and Draft PR creation/update.

Ask before actions with material data, security, architecture, or irreversibility risk, including:

- modifying/deleting real personal data in `/data/odyssey/vault`;
- destructive migrations, database/volume resets, or important live-workflow deletion;
- credential, OAuth-scope, permission, filesystem, network, Cloudflare, or other security-boundary changes;
- new services or material architecture outside the approved scope;
- force pushes/destructive Git history rewrites;
- direct pushes to `main`;
- merging a Pull Request;
- material product/contract ambiguity that cannot be inferred safely.

Routine implementation risk means proceed; material authority/security/data risk means ask. A failed final verification means the branch is not ready, not that coherent work should be discarded.

## Product ambiguity and inference

Do not turn an unstated assumption into settled product behavior. When a user-facing behavior,
retention rule, navigation model, domain semantic, lifecycle, or phase boundary has more than one
plausible interpretation and the canonical documentation does not already decide it, stop and ask the
human before implementing or documenting one interpretation as the product contract.

Do not treat nearby features, historical behavior, analogy with another product, implementation
convenience, or a likely user preference as authorization. During phase definition, surface uncertain
choices explicitly as **open decisions** and resolve them with the human before opening an
implementation PR when the user has asked to define the phase first. Routine mechanical choices
inside an already approved contract remain autonomous.

The fail-closed principle applies to product definition as well as mutation safety: when the product
contract is genuinely unknown, preserve the uncertainty rather than filling the gap with a guess.

## Significant functional phases

For a significant functional phase:

1. read the canonical [Functional Roadmap](docs/architecture/functional-roadmap.md);
2. read the relevant current architecture contracts and ADRs;
3. define objective, acceptance criteria, out-of-scope work, and open decisions under the [Development Pipeline](docs/architecture/development-pipeline.md);
4. run the repository `odyssey-architecture-challenge` skill before implementation;
5. implement code and tests together;
6. run focused checks during iteration and `odyssey-verify-change` before declaring readiness;
7. create/maintain a Draft PR until deterministic CI and semantic review are clean;
8. human merge only;
9. after merge, use `odyssey-post-merge` for safe synchronization/branch cleanup when the local environment is available.

When discussion creates a real future requirement or functional direction, preserve it in the roadmap or the appropriate canonical future-direction document. Do not leave project direction only in chat, an issue, a PR description, or agent memory.

## Operational learning and incident closure

When a non-trivial bug, deployment drift, hidden precondition, environment mismatch, or operational failure is diagnosed, the task is not complete when the immediate symptom disappears. Preserve the reusable learning before closing the work.

- Record the learning in the smallest canonical owner: phase/benchmark docs for checkpoint evidence, infrastructure/runbook docs for operational recovery, architecture/storage docs for durable invariants, and future-direction docs for deferred product work.
- Capture only what will help the next occurrence: **symptom or trigger, affected boundary, root cause, corrective action, verification evidence, and the preventive diagnostic/check**. Add rollback/safety constraints when the fix touches live data, security, credentials, networking, or deployment state.
- Prefer converting a discovered failure mode into an executable guard when practical: deterministic test, preflight assertion, deployment fingerprint/drift check, health probe, validation command, or runbook checklist. If automation is not justified yet, document the manual check explicitly.
- Distinguish **observed live state** from intended/configured state. Never document a live fix, migration, activation, or cleanup as complete until its post-change verification has actually passed.
- Before a live network/security mutation, inspect the complete current scope and the installed CLI/API semantics. Do not substitute broad commands such as `off`, `reset`, bulk replace, or recreate for an authorized narrow diff unless the live scope has already been proven to contain only that target and the authorization explicitly covers the broader effect.
- If read-only evidence or a mutation preflight contradicts an earlier diagnosis, stop and reconcile the live representation before mutating. If an approval system and execution transcript disagree about whether a command ran, treat the live state as `UNKNOWN` and perform read-only post-state verification before any further change.
- Do not treat a forwarded header name as proof of provenance. When identity or authorization depends on a proxy-added header, enumerate every ingress that can reach the same consumer and prove the relevant traffic crosses the trusted validation boundary or validate the assertion again at the consumer.
- Prefer authoritative provider documentation plus effective configuration evidence over inspecting real user tokens or identity payloads when those sources are sufficient to establish a security contract.
- Do not turn `AGENTS.md` into an incident log. This section defines the capture discipline; actual incidents and solutions belong in their canonical technical owner and should be linked instead of duplicated.
- If a debugging path required multiple layers to isolate the fault, preserve the shortest reusable boundary-isolation method so future agents do not repeat broad trial-and-error.

The [Development Pipeline](docs/architecture/development-pipeline.md) owns the detailed close-the-loop process. Git/PR history alone is not a substitute for a still-needed operational invariant or recovery procedure.

## Implementation routing

Use the smallest executor that can validate the work reliably:

- a GitHub-capable agent is appropriate for bounded documentation/status changes, PR review, and small well-understood code changes whose validation can rely on deterministic CI;
- use Codex when local repository execution, iterative debugging/testing, broad multi-file implementation, benchmark work, Raspberry/Docker/filesystem access, or environment interaction materially improves reliability.

The author never gains merge authority. Deterministic CI, semantic review, and human merge remain separate gates.

## User-facing agent prompts

When preparing a prompt for Codex or another development agent for the user:

- write the reusable prompt in English unless the user explicitly asks for another language;
- always accompany it with a concise Spanish summary explaining the objective, what the agent is expected to do, and the important safety/cost constraints;
- include the recommended model and reasoning effort, with a short cost/capability rationale when model choice is relevant;
- do not omit the summary just because the prompt itself is long.

### Codex model-selection guidance

Recommend the **cheapest model and reasoning level that still has comfortable capability margin for the task's risk and complexity**. Do not default habitually either to the cheapest model or to the strongest model. State the recommendation explicitly in each ChatGPT-to-Codex handoff and give a short reason so the human can judge the cost/capability trade-off.

Use task risk, ambiguity, cross-boundary reasoning, and likely change amplification as the main signals. The current practical heuristic is:

- small mechanical edits, bounded documentation/tests, or already-diagnosed fixes -> prefer the cheapest capable tier, typically Luna Low/Medium when available;
- ordinary implementation with a settled contract and moderate multi-file reasoning -> prefer the middle capability tier, typically Terra Medium/High when available;
- architecture challenges, ambiguous cross-boundary debugging, security/networking/production incidents, or decisions where a wrong conclusion can amplify into substantial rework -> prefer Sol High;
- escalate beyond that only when evidence shows the lower recommendation is insufficient.

These model names are examples of the current lineup, not a permanent task-to-model binding. Re-evaluate as model capabilities, pricing, and availability change while preserving the cost/risk principle. Do not downgrade a high-risk task solely to save tokens when error amplification is likely, and do not spend Sol-class capacity on routine work merely by habit.

### ChatGPT-to-agent handoff communication preference

This is an assistant-facing communication preference for the ChatGPT project assistant,
not an execution instruction for Codex or another implementation agent. Before ChatGPT
gives the user a Codex prompt, it should briefly explain in Spanish what is happening
functionally and technically, why the Codex step is needed, which component or boundary
is involved, what Codex will touch and deliberately leave untouched, and what result is
expected. After the user returns Codex output, ChatGPT should first explain in Spanish
what Codex found or changed, what that means functionally, what happened technically,
whether it matches the expected architecture and safety contract, and what is unblocked
or remains pending. Keep the explanation concise but informative; use a small ASCII
diagram when it materially clarifies the handoff.

## Documentation ownership

Odyssey deliberately keeps few **canonical owners** and links to them instead of copying their content.

```text
README / product vision        -> product entry point and durable promise
overview                       -> current architecture
functional-roadmap             -> current phase/status and intended order
knowledge-model-direction      -> current knowledge representation
note-schema + JSON             -> schema interpretation + exact machine schema
storage                        -> data authority/storage ownership
future-* / platform directions -> intentionally deferred contracts
phase docs / ADRs / benchmarks -> historical contract/evidence
```

Rules:

- Current status belongs in `functional-roadmap.md`, not repeated across historical phase documents.
- Current system shape belongs in `overview.md`; phase documents may preserve checkpoint-local wording for historical evidence.
- Exact schema fields/types live in `config/note-schema.json`; prose explains principles and boundaries rather than copying the registry.
- One future capability should have one detailed owner. `future-extension-points.md` is primarily an index plus cross-cutting directions that do not have their own document.
- Do not create a separate Markdown document for every function, workflow, benchmark, or subphase when source code, tests, an ADR, or an existing canonical document already owns the durable contract.
- When a document becomes historical, keep it only if it preserves evidence/decisions not captured elsewhere; otherwise consolidate safely and update links.
- Documentation cleanup must not erase why a safety or architecture decision was made. Git/PR history is not a substitute for a still-needed durable contract, but it is sufficient for routine transient implementation detail.

## GitHub review workflow

Default to **one active PR at a time**. Do not open Draft PRs merely to remember future ideas or deferred product directions; preserve those in the canonical roadmap or appropriate future-direction owner instead. Multiple open PRs are appropriate only when a real dependency, review, or sequencing reason makes parallel/stacked work useful, and that dependency must be explicit. Before opening another PR, inspect the existing open PR set and merge, close, or consolidate obsolete/documentation-only work so deferred decisions do not become forgotten backlog.

Before continuing implementation on a branch with an open PR, use `odyssey-pr-feedback` to inspect review feedback. If comments conflict with each other or with an approved material contract, ask rather than guessing.

Use `odyssey-verify-change` before declaring a PR complete/ready. Verification is required for readiness; a safe checkpoint commit may still record an incomplete or blocked state explicitly.

Never delete an unmerged branch or a branch whose merge relationship is uncertain. Human approval is required for merge/deployment/security/destructive/credential/network/real-vault changes.
