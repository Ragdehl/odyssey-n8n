# Phase 17E common metadata review

Status: **COMPLETED**

This supporting decision record belongs to the Phase 17E schema utility review. It records the common-metadata decisions separately from the type-by-type review so implementation changes can be applied and validated coherently.

## Common identity metadata

- `id` — **KEEP / Core-owned**. Stable machine identity independent of filename and current display name.
- `name` — **KEEP / Core-owned**. Canonical human-readable identity.
- `type` — **KEEP / Core-owned mechanism**. Core owns validation/registration of the type field even when a registered value is semantically owned by an application/domain.
- `subtype` — **DEFER**. No current subtype is registered and the planner does not expose subtype behavior. Reintroduce only when a concrete stable `is-a` specialization unlocks useful behavior.

## Lifecycle and safety metadata

- `created_at` — **KEEP / Core-owned**. Note lifecycle creation timestamp, distinct from domain dates.
- `updated_at` — **KEEP / Core-owned**. Latest Odyssey mutation timestamp.
- `revision` — **KEEP / Core-owned**. Supports fail-closed optimistic concurrency and safe writes when the authoritative note changes after planning.
- `schema_version` — **KEEP / Core-owned**. Supports validation and explicit schema migration.
- `deleted` — **KEEP / Core-owned**. Recoverable soft-delete marker; deleted notes are excluded from ordinary active resolution/retrieval.
- `aliases` — **KEEP / Core-owned identity evidence**. Alternative names for the same stable identity. Do not infer/promote aliases automatically without an explicit safe contract.

## Provenance: `created_by` / `updated_by`

**KEEP, but change the current scalar string representation.** Provenance needs to distinguish the human who originated the intent from the application/capability that executed the mutation.

Prefer a named structure rather than a positional tuple:

```yaml
created_by:
  human: <stable-user-id-or-null>
  app: <stable-app-id-or-null>

updated_by:
  human: <stable-user-id-or-null>
  app: <stable-app-id-or-null>
```

Rules:

- at least one of `human` or `app` must be non-null;
- `human` represents the human originator/intent when one exists;
- `app` represents the application/capability that executed or originated the autonomous action;
- direct human action may have `app: null`;
- autonomous app action may have `human: null`;
- a human request executed by an app records both;
- human identity uses stable user IDs, not display names;
- this provenance is not itself the future authorization model. Authentication/authorization and sharing remain separate contracts.

Canonical schema-v3 notes store and validate named `{human, app}` provenance objects. Legacy scalar actor inputs remain accepted only at the bounded persistence input-normalization boundary; no persisted-v2 read migration is defined here.

## Tags

### Core ownership decision

`tags` are **not Core-owned semantics**.

Core provides a generic free-form tag storage/validation mechanism, but Core must not decide what tags exist or infer when they apply. Tag vocabulary and inference/application policy belong to the user or to the application/domain that needs them.

```text
Core
  -> generic storage / validation contract when needed
  -> no built-in semantic vocabulary
  -> no tag inference policy

User or app/domain
  -> defines useful tags
  -> decides when they apply
  -> may infer them from natural language under that app's explicit policy
```

### Current built-in vocabulary

Remove the current Core-owned semantic vocabulary as part of the Phase 17E schema simplification:

- `idea` — **REMOVE from Core vocabulary**
- `decision` — **REMOVE from Core vocabulary**
- `question` — **REMOVE from Core vocabulary**
- `reflection` — **REMOVE from Core vocabulary**
- `reference` — **REMOVE from Core vocabulary**
- `hypothesis` — **REMOVE from Core vocabulary**
- `explore` — **REMOVE from Core vocabulary**
- `someday` — **REMOVE from Core vocabulary**
- `review` — **REMOVE from Core vocabulary**

The main reason is that Phase 17D made atomic facts the meaningful knowledge units inside an entity note. Labels such as `decision`, `question`, or `reflection` often describe an individual fact rather than the entire entity note. Workflow-like labels such as `review`, `someday`, or `explore` are better owned by the applications that implement those behaviors.

### `tags` field itself

**KEEP as a generic Core mechanism.** Core owns optional `tags` storage, validation, explicit add/remove mutation, and exact membership filtering. Tag values remain free-form and user/app chosen; Core defines no vocabulary, registry, controlled IDs, semantic meaning, or inference policy.

The planner retains only an explicit-only `TagChange` mechanism for free-form values, and retrieval exposes exact `tags contains` filtering without any registry.

## Future effective-schema composition

Future application work must compose an effective schema at an explicit boundary:

```text
Core schema + installed app/domain contributions
        -> validated effective schema
        -> planner capabilities
        -> Sol
```

An application may add supported properties to existing types, register genuinely new types, and contribute guidance without redefining the fundamental Core meaning of an existing type. Collisions and incompatible contributions must be detected before the effective schema is exposed to planning or persistence. This is a future extension requirement, not Phase 17E implementation scope.

## Implementation consequences to validate

Phase 17E implementation should explicitly evaluate and test:

1. removal/deferment of active `subtype` behavior;
2. removal of current `person.birth_date` and `person.relationship_to_user` from the minimal Core-owned contract while preserving their future domain-extension direction;
3. structured provenance migration for `created_by` / `updated_by`;
4. removal of the built-in tag vocabulary and Core tag-planning/filter machinery that no longer has a product requirement;
5. compatibility/migration of existing test fixtures and notes;
6. preservation of safe identity, revision, soft-delete, alias, and schema-version behavior.
