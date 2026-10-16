# E3 shared canonical mutation gate

## Inventory and decision (16-10-2026)

Canonical Markdown remains the sole authority.  E3 does not add a writer,
database, semantic planner, or application-to-Core dependency.  The smallest
safe common boundary is `odyssey_core.mutation_gate.CanonicalMutationGate`:
it re-grounds an already authenticated stable target ID in Markdown, checks
revision plus SHA-256 source token and expected type, validates trusted actor
provenance, records history where available, and returns a validated physical
readback receipt.  The domain service still decides whether an operation is
valid and calls the existing Core materializer/persistence function.

| Entry point | Current canonical writer | E3 status | Domain checks retained |
| --- | --- | --- | --- |
| Chat Core | `application.execute_request` -> `materialization` -> `persistence` | already uses the authoritative materializer; not wrapped because it can affect independent Notes and E3 has no transaction claim | Core plan, preflight, references, candidate coverage |
| Direct Notes delete | `direct_note_mutations` -> `materialize_update/delete` | uses gate precondition, history and readback receipt | exact fact locator; incoming backlinks |
| Task checkbox | `TaskDirectMutationService` -> `materialize_update` | uses gate precondition, history and readback receipt | task type and valid status transition |
| Task subtask create | `TaskDirectMutationService` -> `materialize_create` | shared CREATE receipt; parent is rechecked immediately before materialization | parent status, Core preflight and parent reference |
| Work Sessions | `TaskWorkSessionService` -> `create_entity/update_entity/soft_delete_entity` | shared CREATE/update/delete pre/post receipt | global active session, Task owner, interval/activity lifecycle |
| Calendar | `materialization.materialize_calendar_day_record` and chat path | already materializes through Core; query app has no mutation API | deterministic Day identity/link guards |

## Guarantee matrix

The gate's `MutationCommand` has no user source text and cannot select a note
semantically.  `prepare` rejects malformed commands, duplicate/deleted IDs,
wrong types, forged/stale revision/hash values and invalid actor provenance.
`execute_prepared` invokes an injected callable (Protocol composition, no app
switch), then checks that the persistence result is for the expected exact
path/ID and reads canonical Markdown back with schema validation.  A history
failure is represented in the receipt and does not erase a verified write.
There is intentionally no multi-note atomicity promise.  If a dependent step
fails after a known physical result, `receipt_after_write` preserves the
readback receipt for a partial outcome; callers must not blind-replay it.

## Residual gaps

CREATE is now supported with `CreateMutationCommand`: it verifies that the
new stable ID is absent, rechecks an optional parent command immediately before
the one persistence call, validates the created Markdown/type/identity, and
records optional verified affected IDs. Work Session start rechecks the active
session invariant immediately before create. The filesystem repository has no
cross-file transaction/lock, so two independent processes can still race
between that check and file creation; E3 does not claim serializable global
session creation.

Chat's existing per-unit receipts remain its established execution contract.
Calendar currently exposes queries only. Derived-index refresh remains owned
by existing runtime/materialization flows; E3 has not introduced a competing
index refresher. `TaskCorePlanner` generic reference rewriting was inspected
but is not moved in this increment: it combines Tasks UI-visible action and
Task-specific relationship roles, so extracting it without a tested Core
extension contract would be a risky semantic refactor.

## E3 hardened follow-up (16-10-2026, local, not deployed)

- Direct Notes, Task and Work Sessions preserve `CanonicalPostwriteError` as bounded public `POSTWRITE_UNVERIFIED` with `physical_write: true` and canonical stable target ID, rather than returning a false no-write rejection. The gate's typed error retains `EntityPersistenceResult`; receipt failures do not trigger automatic replay. Runtime HTTP keeps status 409 and includes an explicit `partial` field. This receipt is evidence of a *known physical persistence call*, not proof that downstream projection/index completed.
- `execute_prepared` now revalidates ID/type/revision/SHA-256 from the single previously grounded file immediately before the domain writer. Its first `prepare` retains canonical identity ambiguity scanning; no second O(vault) sweep was introduced. This is not cross-process atomic compare-and-swap.
- Runtime direct UI mutation requests with `request_id` share the same actor-root immutable `LocalDeliveryResultStore` backend already used by product deliveries, under a separate `notes-mutation-results` namespace, and a reentrant mutation serialization lock. Request fingerprint binds actor-state root, operation and full canonical payload. A repeated completed delivery returns its old response without another writer/refresh. A conflicting reuse fails before writing. The `*.claim` file is an actor-local durable before-write reservation created atomically (`O_EXCL`) and only removed once the final immutable response exists: an interrupted post-write delivery remains unavailable for blind replay and requires explicit reconciliation. Fail-closed pending claims (including prewrite exceptions) have no automatic expiration; future claim reconciliation remains an operational support requirement. Lock serialization is in-process; O_EXCL claim protects identical IDs across processes, not distinct-ID global domain invariants.
- Failed result-store final save or optional index refresh after a known successful physical mutation preserves the original operation with an explicit `partial.physical_write` flag. Work Session list projection failure after write likewise returns an explicit partial without inventing a successful list. Rebuildable indexes and list presentation are not the canonical write.
- Adversarial tests use disposable vaults: a body change retaining the same revision is rejected by hash after `prepare`; exact readback failure after a persisted write produces a typed partial; simultaneous same-ID `work_session_start` calls write once; a simulated failed receipt save leaves a durable claim and prohibits second physical write; Task subtask creation replay and work-session CRUD are exercised through `RuntimeComposition.notes`. Actual HTTP server Notes routes tested separately with loopback sockets.
- **Validated outside Codex's network-restricted sandbox:** Python `pytest -q --tb=no`: **3327 passed, 80 skipped, same ten historical failures, 52 subtests passed**, no new failures; Node `node --test tests/*.test.mjs tests/*.test.js`: **180 passed, 0 failed**. HTTP test `tests/runtime/test_runtime_boundary.py`: **55 passed** outside the sandbox. The Codex workspace sandbox prohibited loopback socket binds, generating 32 apparent HTTP test errors in its own internal execution; these are environmental, not new functional failures, as proved by rerun outside. Ruff check and formatting, schema pre-commit and `git diff --check` must pass before final commit. No real provider calls.

### Explicit E3 remaining acceptance gates

This branch is **not yet the fully adopted DEV end-to-end product**. E2E in the developer tests means Python/HTTP/actor/runtime/Markdown readback with disposable repositories; it does **not** mean this exact commit has travelled through DEV's deployed n8n Router→Temporal→Planner→Core→Calendar→browser/DOM graph. That real DEV/n8n/browser vertical, including a fresh user-originated message and observed UI, requires a later controlled DEV deploy and corresponding acceptance. Chat Core's already established multi-note receipts and Calendar's deterministic materialization use the same canonical persistence but are not migrated into this *single-note* gate; there is no new competing materializer. Cross-file active Work Session exclusivity under distinct requests across multiple server processes remains non-serializable without a filesystem-wide lock/transaction (not promised). General `TaskCorePlanner` semantic rewrite extraction remains deferred pending a separately tested Core extension contract. A receipt cannot be recovered automatically from an interrupted delivery claim with no completed response: reconcile against canonical vault and history before allowing a new request.

## E3 hardening — actor-local direct mutation replay and partial outcomes (16-10-2026)

- `RuntimeComposition.notes` serializes the entire load/execute/save operation for any direct mutation carrying a request ID. Ordinary Notes reads continue without writer locking. Actor-isolated `LocalDeliveryResultStore` preserves successful UI mutation responses by a fingerprint of operation, complete payload and trusted actor state root, independently of chat delivery records. Reuse with a different payload is rejected before another mutation; concurrent identical requests within one runtime execute only once.
- Each direct UI mutation receives an atomic durable `claim_mutation` reservation **before** the physical write. On process interruption after Markdown is written but before the immutable final result is saved, the unresolved claim prevents blind replay. This is **at-most-once execution, not automatic completion/recovery**; such attempts need explicit reconciliation. Different request IDs and separate runtime processes are not serialized by the in-process lock.
- `CanonicalMutationGate.execute_prepared` re-reads the exact prepared path and checks ID, revision, type and SHA-256 before executing; the gate does not add a second full-vault rescan at that point. A known returned persistence result followed by failed readback raises a typed `CanonicalPostwriteError` with bounded target evidence, propagated through Notes, Tasks, Work Sessions and the HTTP response with `partial.physical_write=true`.
- Runtime-derived index refresh and Work Session list projection failures after a verified write now preserve the physical result with a `partial` marker; a failed durable receipt save also returns an explicit partial marker. This must not be mistaken for a successful index refresh or a replayable final receipt.
- Regression evidence outside Codex's restricted socket sandbox: 129 backend E2E tests across eight source/message/graph suites passed; 55 HTTP runtime boundary tests passed; 62 relevant runtime/Notes tests passed; dedicated concurrent same-ID Work Session create, conflicting replay ID, simulated unpersisted receipt, stale prepared Note, partial index refresh and fake App adapter tests passed in disposable vaults. Final post-change full suite (remote shell, outside restricted Codex sandbox): **3328 Python pass, 80 skip, exactly ten pre-existing historical benchmark/pricing failures**, **180 Node pass**; Ruff, format and `git diff --check` pass. This is a known non-green global baseline, not a clean overall pytest pass.

**Remaining acceptance risks:** The gate's initial stable-ID lookup and create uniqueness check still scan the vault; no latency improvement should be claimed until indexing and physical-read benchmarks demonstrate it. Chat Core's multi-note result/receipt contract and Calendar Day composition are existing authoritative Core paths but not migrated to this single-note gate. The filesystem does not provide cross-note atomic transactions or serializable multi-process global Work Session active-session enforcement; no such guarantee is claimed. The note/browser→n8n→runtime→Markdown→graph **live DEV vertical** has not been deployed or exercised with these E3 changes.
