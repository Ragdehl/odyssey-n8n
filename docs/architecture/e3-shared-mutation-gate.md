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
